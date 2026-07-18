/* app.js — 3D BuggyBoy course viewer/editor (three.js).
 *
 * Fetches the course model from the Flask backend (path traced from the leg's track-map,
 * elevation from the record stream) and builds a drivable 3D road ribbon with roadside-object
 * markers. Orbit to inspect, or drive along the course; edit segment slopes live.
 */
const PATH_SCALE = 3.0;      // track-map pixel -> world unit
const ELEV_WORLD = 7.0;      // elevation model unit -> world height
const OBJ_OUT = 1.5;         // object offset beyond the road edge (x halfWidth)

let scene, camera, renderer, controls;
let roadGroup = null, course = null, leg = 0;
let mode = "orbit";          // "orbit" | "drive"
const keys = {};             // held keys for drive
let driveS = 0, driveSpeed = 0;

const $ = (id) => document.getElementById(id);
const status = (m) => { $("status").textContent = m; };

// ---- world position of path point i (bitmap x -> X, elevation -> Y, bitmap y -> Z) ----
function worldPos(i) {
  const p = course.path[i];
  return new THREE.Vector3(p[0] * PATH_SCALE, course.elevation[i] * ELEV_WORLD, p[1] * PATH_SCALE);
}
// unit normal in the XZ plane at point i (perpendicular to the local tangent)
function normalAt(i) {
  const a = worldPos(Math.max(0, i - 1)), b = worldPos(Math.min(course.path.length - 1, i + 1));
  const t = new THREE.Vector3().subVectors(b, a); t.y = 0; t.normalize();
  return new THREE.Vector3(-t.z, 0, t.x);
}

function buildRoad() {
  if (roadGroup) { scene.remove(roadGroup); roadGroup.traverse(o => o.geometry && o.geometry.dispose()); }
  roadGroup = new THREE.Group();
  const n = course.path.length;
  const hw = course.halfWidth * PATH_SCALE;

  // ribbon geometry: two vertices (left/right edge) per path point
  const pos = [];
  for (let i = 0; i < n; i++) {
    const c = worldPos(i), nrm = normalAt(i);
    pos.push(c.x + nrm.x * hw, c.y, c.z + nrm.z * hw);
    pos.push(c.x - nrm.x * hw, c.y, c.z - nrm.z * hw);
  }
  const idx = [];
  for (let i = 0; i < n - 1; i++) {
    const a = 2 * i;
    idx.push(a, a + 1, a + 2, a + 2, a + 1, a + 3);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geo.setIndex(idx);
  geo.computeVertexNormals();
  const road = new THREE.Mesh(geo, new THREE.MeshStandardMaterial(
    { color: 0x3a3f4b, side: THREE.DoubleSide, roughness: 0.95 }));
  roadGroup.add(road);

  // roadside object markers
  const box = new THREE.BoxGeometry(1.4, 3, 1.4);
  for (const o of course.objects) {
    const i = Math.round(o.t * (n - 1));
    const c = worldPos(i), nrm = normalAt(i);
    const off = hw + OBJ_OUT * PATH_SCALE;
    const col = new THREE.Color().setHSL((o.type % 32) / 32, 0.6, 0.55);
    const m = new THREE.Mesh(box, new THREE.MeshStandardMaterial({ color: col }));
    m.position.set(c.x + nrm.x * off * o.side, c.y + 1.5, c.z + nrm.z * off * o.side);
    roadGroup.add(m);
  }
  scene.add(roadGroup);
}

async function loadCourse(newLeg) {
  leg = newLeg;
  status("loading leg " + leg + " …");
  course = await (await fetch("/api/course/" + leg)).json();
  buildRoad();
  buildSegPanel();
  frameCamera();
  driveS = 0; driveSpeed = 0;
  [...$("legs").children].forEach((b, i) => b.classList.toggle("active", i === leg));
  status(`leg ${leg}: ${course.path.length} path points, ${course.objects.length} objects`);
}

function frameCamera() {
  // point the orbit target at the course centre, back the camera off to see it all
  const box = new THREE.Box3().setFromObject(roadGroup);
  const c = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3()).length();
  controls.target.copy(c);
  camera.position.set(c.x, c.y + size * 0.5, c.z + size * 0.6);
  camera.far = size * 8; camera.updateProjectionMatrix();
}

// ---- drive: follow the path; W/S throttle, A/D steer the look ----
let driveYaw = 0;
function updateDrive(dt) {
  const n = course.path.length;
  if (keys["w"]) driveSpeed = Math.min(30, driveSpeed + 20 * dt);
  else if (keys["s"]) driveSpeed = Math.max(-10, driveSpeed - 20 * dt);
  else driveSpeed *= 0.96;
  if (keys["a"]) driveYaw += 1.2 * dt;
  if (keys["d"]) driveYaw -= 1.2 * dt;

  driveS += driveSpeed * dt;
  if (driveS < 0) driveS += n; if (driveS >= n) driveS -= n;
  const i = Math.floor(driveS) % n, j = (i + 1) % n, f = driveS - Math.floor(driveS);
  const p = worldPos(i).lerp(worldPos(j), f);
  const ahead = worldPos((i + 4) % n);
  camera.position.set(p.x, p.y + 4, p.z);
  const look = ahead.clone();
  // apply steer yaw around the up axis about the camera
  const dir = new THREE.Vector3().subVectors(look, p).applyAxisAngle(new THREE.Vector3(0, 1, 0), driveYaw);
  camera.lookAt(p.clone().add(dir));
}

function animate() {
  requestAnimationFrame(animate);
  const dt = Math.min(0.05, clock.getDelta());
  if (mode === "drive" && course) updateDrive(dt);
  else controls.update();
  renderer.render(scene, camera);
}

// ---- segment slope editor ----
function buildSegPanel() {
  const el = $("segs"); el.innerHTML = "";
  for (const s of course.segments) {
    const row = document.createElement("div"); row.className = "seg";
    row.innerHTML = `<span class="lbl">seg ${s.i}</span>
      <button data-d="-1">–</button><span class="val" id="sv${s.i}">${s.slope}</span>
      <button data-d="1">+</button>`;
    const val = row.querySelector(".val");
    row.querySelectorAll("button").forEach(b => b.onclick = async () => {
      const nv = Math.max(-3, Math.min(4, parseInt(val.textContent) + parseInt(b.dataset.d)));
      await fetch("/api/edit", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ leg, k: s.i, field: "slope", value: nv }) });
      val.textContent = nv; s.slope = nv;
      course = await (await fetch("/api/course/" + leg)).json();   // refetch -> new elevation
      buildRoad();
      status(`seg ${s.i} slope := ${nv}`);
    });
    el.appendChild(row);
  }
}

// ---- init ----
let clock;
function init() {
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0b0e13);
  scene.fog = new THREE.Fog(0x0b0e13, 200, 900);

  camera = new THREE.PerspectiveCamera(60, innerWidth / innerHeight, 0.5, 4000);
  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(innerWidth, innerHeight);
  renderer.setPixelRatio(devicePixelRatio);
  $("scene").appendChild(renderer.domElement);

  controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;

  scene.add(new THREE.HemisphereLight(0xbfd4ff, 0x20242c, 0.9));
  const sun = new THREE.DirectionalLight(0xffffff, 0.7); sun.position.set(1, 2, 1); scene.add(sun);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(6000, 6000),
    new THREE.MeshStandardMaterial({ color: 0x141a12 }));
  ground.rotation.x = -Math.PI / 2; ground.position.y = -20; scene.add(ground);

  // leg buttons
  for (let i = 0; i < 5; i++) {
    const b = document.createElement("button"); b.textContent = "leg " + i;
    b.onclick = () => loadCourse(i); $("legs").appendChild(b);
  }
  $("mode").onclick = () => {
    mode = mode === "orbit" ? "drive" : "orbit";
    $("mode").textContent = "mode: " + mode;
    $("mode").classList.toggle("active", mode === "drive");
    if (mode === "orbit") frameCamera();
  };
  $("save").onclick = async () => {
    const r = await (await fetch("/api/save", { method: "POST" })).json();
    status("saved " + r.path);
  };
  addEventListener("keydown", e => keys[e.key.toLowerCase()] = true);
  addEventListener("keyup", e => keys[e.key.toLowerCase()] = false);
  addEventListener("keypress", e => { if (e.key.toLowerCase() === "m") $("mode").click(); });
  addEventListener("resize", () => {
    camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
  });

  clock = new THREE.Clock();
  loadCourse(0);
  animate();
}

init();
