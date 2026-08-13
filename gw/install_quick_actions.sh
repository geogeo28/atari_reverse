#!/bin/bash
# Install the two Finder Quick Actions (right-click → Quick Actions) for Atari disk images.
#   install_quick_actions.sh              install/refresh both actions
#   install_quick_actions.sh --uninstall  remove both actions
#
# Each action is a generated .workflow bundle whose only job is to exec the matching repo
# script with the selected paths — the logic lives in gw/qa_*.sh, under version control and
# editable without regenerating anything.
set -euo pipefail

readonly GW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SERVICES_DIR="$HOME/Library/Services"
readonly PBS_BIN="/System/Library/CoreServices/pbs"
readonly PLUTIL_BIN="/usr/bin/plutil"
readonly UUIDGEN_BIN="/usr/bin/uuidgen"

readonly SHELL_ACTION_DIR="/System/Library/Automator/Run Shell Script.action"
readonly SHELL_ACTION_VERSION="2.0.3"
readonly ACTION_SHELL="/bin/bash"
# "Run Shell Script" input methods: 0 = pipe paths to stdin, 1 = pass them as arguments ("$@").
readonly INPUT_METHOD_AS_ARGUMENTS=1

readonly MOUNT_ACTION_NAME="Mount Atari ST Disk"
readonly RUN_ACTION_NAME="Run in Hatari"

# NSSendFileTypes takes UTIs, and .st/.stx/.msa have none registered on macOS — they resolve to
# per-machine dyn.* types. Accepting public.item and rejecting the wrong extension inside the
# script is the only filter that behaves the same on every Mac.
readonly ACCEPTED_UTI="public.item"

# Everything interpolated into the generated plists passes through here. The repo path is
# attacker-free but not character-free: a '&', '<' or '>' anywhere in it produced invalid XML,
# which aborted the install midway and left one bundle broken and the other stale.
xml_escape() {
  local text="${1//&/&amp;}"
  text="${text//</&lt;}"
  printf '%s' "${text//>/&gt;}"
}

# Two layers, in this order: %q makes the path safe for the bash that Automator runs, then the
# XML escape makes the whole command safe for the plist that carries it. A path containing a
# single quote silently produced a no-op action before the %q.
build_command_string() {
  xml_escape "exec $(printf '%q' "$1") \"\$@\""
}

emit_info_plist() {
  local menu_name="$1"
  cat <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>NSServices</key>
	<array>
		<dict>
			<key>NSBackgroundColorName</key>
			<string>background</string>
			<key>NSIconName</key>
			<string>NSActionTemplate</string>
			<key>NSMenuItem</key>
			<dict>
				<key>default</key>
				<string>${menu_name}</string>
			</dict>
			<key>NSMessage</key>
			<string>runWorkflowAsService</string>
			<key>NSRequiredContext</key>
			<dict>
				<key>NSApplicationIdentifier</key>
				<string>com.apple.finder</string>
			</dict>
			<key>NSSendFileTypes</key>
			<array>
				<string>${ACCEPTED_UTI}</string>
			</array>
		</dict>
	</array>
</dict>
</plist>
PLIST
}

emit_wflow() {
  local command_string="$1"
  local action_uuid input_uuid output_uuid
  action_uuid=$("$UUIDGEN_BIN"); input_uuid=$("$UUIDGEN_BIN"); output_uuid=$("$UUIDGEN_BIN")
  cat <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>AMApplicationBuild</key>
	<string>521</string>
	<key>AMApplicationVersion</key>
	<string>2.10</string>
	<key>AMDocumentVersion</key>
	<string>2</string>
	<key>actions</key>
	<array>
		<dict>
			<key>action</key>
			<dict>
				<key>AMAccepts</key>
				<dict>
					<key>Container</key>
					<string>List</string>
					<key>Optional</key>
					<true/>
					<key>Types</key>
					<array>
						<string>com.apple.cocoa.string</string>
					</array>
				</dict>
				<key>AMActionVersion</key>
				<string>${SHELL_ACTION_VERSION}</string>
				<key>AMApplication</key>
				<array>
					<string>Automator</string>
				</array>
				<key>AMParameterProperties</key>
				<dict>
					<key>COMMAND_STRING</key>
					<dict/>
					<key>CheckedForUserDefaultShell</key>
					<dict/>
					<key>inputMethod</key>
					<dict/>
					<key>shell</key>
					<dict/>
					<key>source</key>
					<dict/>
				</dict>
				<key>AMProvides</key>
				<dict>
					<key>Container</key>
					<string>List</string>
					<key>Types</key>
					<array>
						<string>com.apple.cocoa.string</string>
					</array>
				</dict>
				<key>ActionBundlePath</key>
				<string>${SHELL_ACTION_DIR}</string>
				<key>ActionName</key>
				<string>Run Shell Script</string>
				<key>ActionParameters</key>
				<dict>
					<key>COMMAND_STRING</key>
					<string>${command_string}</string>
					<key>CheckedForUserDefaultShell</key>
					<true/>
					<key>inputMethod</key>
					<integer>${INPUT_METHOD_AS_ARGUMENTS}</integer>
					<key>shell</key>
					<string>${ACTION_SHELL}</string>
					<key>source</key>
					<string></string>
				</dict>
				<key>BundleIdentifier</key>
				<string>com.apple.RunShellScript</string>
				<key>CFBundleVersion</key>
				<string>${SHELL_ACTION_VERSION}</string>
				<key>CanShowSelectedItemsWhenRun</key>
				<false/>
				<key>CanShowWhenRun</key>
				<true/>
				<key>Category</key>
				<array>
					<string>AMCategoryUtilities</string>
				</array>
				<key>Class Name</key>
				<string>RunShellScriptAction</string>
				<key>InputUUID</key>
				<string>${input_uuid}</string>
				<key>Keywords</key>
				<array>
					<string>Shell</string>
					<string>Script</string>
					<string>Command</string>
					<string>Run</string>
					<string>Unix</string>
				</array>
				<key>OutputUUID</key>
				<string>${output_uuid}</string>
				<key>UUID</key>
				<string>${action_uuid}</string>
				<key>UnlocalizedApplications</key>
				<array>
					<string>Automator</string>
				</array>
				<key>arguments</key>
				<dict/>
				<key>isViewVisible</key>
				<integer>1</integer>
				<key>location</key>
				<string>309.000000:253.000000</string>
				<key>nibPath</key>
				<string>${SHELL_ACTION_DIR}/Contents/Resources/Base.lproj/main.nib</string>
			</dict>
			<key>isViewVisible</key>
			<integer>1</integer>
		</dict>
	</array>
	<key>connectors</key>
	<dict/>
	<key>workflowMetaData</key>
	<dict>
		<key>serviceApplicationBundleID</key>
		<string>com.apple.finder</string>
		<key>serviceApplicationPath</key>
		<string>/System/Library/CoreServices/Finder.app</string>
		<key>serviceInputTypeIdentifier</key>
		<string>com.apple.Automator.fileSystemObject</string>
		<key>serviceOutputTypeIdentifier</key>
		<string>com.apple.Automator.nothing</string>
		<key>serviceProcessesInput</key>
		<integer>0</integer>
		<key>workflowTypeIdentifier</key>
		<string>com.apple.Automator.servicesMenu</string>
	</dict>
</dict>
</plist>
PLIST
}

bundle_path_for() {
  printf '%s/%s.workflow' "$SERVICES_DIR" "$1"
}

# The bundle is deliberately dumb: one exec into the repo script, which is the versioned surface.
install_action() {
  local menu_name="$1" target_script="$2"
  local bundle contents
  bundle=$(bundle_path_for "$menu_name")
  contents="$bundle/Contents"

  [ -x "$target_script" ] || { printf 'error: not executable: %s\n' "$target_script" >&2; exit 1; }

  rm -rf "$bundle"
  mkdir -p "$contents"
  emit_info_plist "$(xml_escape "$menu_name")" >"$contents/Info.plist"
  emit_wflow "$(build_command_string "$target_script")" >"$contents/document.wflow"

  "$PLUTIL_BIN" -lint "$contents/Info.plist" >/dev/null
  "$PLUTIL_BIN" -lint "$contents/document.wflow" >/dev/null
  printf 'installed  %s\n           -> %s\n' "$bundle" "$target_script"
}

uninstall_action() {
  local bundle
  bundle=$(bundle_path_for "$1")
  if [ -d "$bundle" ]; then
    rm -rf "$bundle"
    printf 'removed    %s\n' "$bundle"
  else
    printf 'not found  %s\n' "$bundle"
  fi
}

# pbs caches the Services registry; without this the menu items appear only after a re-login.
refresh_services_registry() {
  "$PBS_BIN" -update
  printf 'refreshed  Services registry (%s -update)\n' "$PBS_BIN"
}

usage() {
  printf 'usage: %s [--uninstall]\n' "${BASH_SOURCE[0]##*/}" >&2
  exit 2
}

main() {
  [ "$#" -le 1 ] || usage
  case "${1:-}" in
    --uninstall)
      uninstall_action "$MOUNT_ACTION_NAME"
      uninstall_action "$RUN_ACTION_NAME"
      ;;
    "")
      mkdir -p "$SERVICES_DIR"
      install_action "$MOUNT_ACTION_NAME" "$GW_DIR/qa_mount_st.sh"
      install_action "$RUN_ACTION_NAME" "$GW_DIR/qa_run_hatari.sh"
      ;;
    *)
      usage
      ;;
  esac
  refresh_services_registry
}

main "$@"
