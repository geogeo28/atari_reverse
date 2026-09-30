"""The object-tree operations' shared staging (`src/aes/objects.c`): their Alcyon signatures, the snapshot's trees the
batteries seed from, and the models the results are held to — a tree's links as the ROM's walks see them.

The two batteries: `test_aes_objects_find.py` (ob_find and the GRECT helpers it calls) and
`test_aes_objects_edit.py` (ob_add, ob_delete, ob_order, get_prev and ob_center).
"""
import aes
import vdi
from aes import signed

OB_FIND = "AES_ROM_OB_FIND"
OB_ADD = "AES_ROM_OB_ADD"
OB_DELETE = "AES_ROM_OB_DELETE"
OB_ORDER = "AES_ROM_OB_ORDER"
OB_FS = "AES_ROM_OB_FS"
OB_ACTXYWH = "AES_ROM_OB_ACTXYWH"
OB_RELXYWH = "AES_ROM_OB_RELXYWH"
OB_SETXYWH = "AES_ROM_OB_SETXYWH"
GET_PREV = "AES_ROM_GET_PREV"
OB_CENTER = "AES_ROM_OB_CENTER"

TREE_OBJECT = (vdi.IMAGE_ARG, vdi.LONG_ARG, vdi.WORD_ARG)
aes.declare_alcyon(OB_FIND, aes.WORD_ANSWER, (*TREE_OBJECT, vdi.WORD_ARG, vdi.WORD_ARG, vdi.WORD_ARG))
aes.declare_alcyon(OB_ADD, None, (*TREE_OBJECT, vdi.WORD_ARG))
aes.declare_alcyon(OB_DELETE, None, TREE_OBJECT)
aes.declare_alcyon(OB_ORDER, None, (*TREE_OBJECT, vdi.WORD_ARG))
aes.declare_alcyon(OB_FS, aes.WORD_ANSWER, (*TREE_OBJECT, vdi.LONG_ARG))
for _name in (OB_ACTXYWH, OB_RELXYWH, OB_SETXYWH):
    aes.declare_alcyon(_name, None, (*TREE_OBJECT, vdi.LONG_ARG))
aes.declare_alcyon(GET_PREV, aes.WORD_ANSWER, (*TREE_OBJECT, vdi.WORD_ARG))
aes.declare_alcyon(OB_CENTER, None, (vdi.IMAGE_ARG, vdi.LONG_ARG, vdi.LONG_ARG))

# THE SNAPSHOT's OWN TREES (the AES's ROM resource, relocated into GEMBSS): the file selector (tree 0, 25 objects four
# deep, an OUTLINED root) and the alert (tree 1, ten objects its builder sizes, OUTLINED too). The selector's shape the
# cases name: the root's eleven children run 1..7 and 21..24; 6 is the file list's box with nine children 12..20, 7 the
# scroll bar with three (8, 9, 10), the last of which has one (11), the deepest.
SELECTOR = aes.resource_tree(0)
ALERT = aes.resource_tree(1)
SELECTOR_OBJECTS = aes.tree_length(SELECTOR)
FIRST_CHILD, LAST_CHILD = 1, 24
FILE_BOX, SCROLL_BAR, SLIDER_TRACK, SLIDER = 6, 7, 10, 11
FIRST_FILE, LAST_FILE = 12, 20


def object_word(image, tree, index, name):
    """Field `name` of object `index` (a signed index: -1 is the object below the tree), as a signed word."""
    return signed(aes.read_field(image, "OB", name, tree + index * aes.OB_BYTES))


def links_of(image, tree, count):
    """`[(next, head, tail)]` of the tree's first `count` objects, as signed words."""
    return [tuple(object_word(image, tree, index, name) for name in ("NEXT", "HEAD", "TAIL")) for index in range(count)]


def children_of(image, tree, parent):
    """`parent`'s children as its head and the ob_next links say, up to the one whose ob_next is the parent."""
    children, child = [], object_word(image, tree, parent, "HEAD")
    while child != aes.OB_NIL and child != parent:
        children.append(child)
        assert len(children) <= aes.TREE_OBJECTS, f"the children of {parent} do not end"
        child = object_word(image, tree, child, "NEXT")
    return children


def parent_by_climbing(tree, index, image):
    """get_par's rule, which needs no tree length: along ob_next to the object whose ob_tail is the one just left.
    Not `aes.parent_of`, the links model get_par's own battery is held to: the two agree on a well-formed tree, and
    this one is what ob_find's model climbs by (the argument order is `aes.parent_of`'s)."""
    if index == aes.OB_ROOT:
        return aes.OB_NIL
    left, parent = index, object_word(image, tree, index, "NEXT")
    while object_word(image, tree, parent, "TAIL") != left:
        left, parent = parent, object_word(image, tree, parent, "NEXT")
    return parent


def screen_origin(image, tree, index):
    """The screen position of object `index` as ob_offset sums it: its and every ancestor's ob_x/ob_y, as words."""
    x = y = 0
    while index != aes.OB_NIL:
        x, y = signed(x + object_word(image, tree, index, "X")), signed(y + object_word(image, tree, index, "Y"))
        index = parent_by_climbing(tree, index, image)
    return x, y


def inside(x, y, rect):
    """rc inside ($feccd6): at or past the origin, short of the word-summed far edge, every compare signed."""
    left, top, width, height = rect
    return left <= x < signed(left + width) and top <= y < signed(top + height)


def find_model(image, tree, start, depth, x, y):
    """ob_find ($fea0a8) as the ROM walks it: a hit descends to the LAST child, a miss among children steps back."""
    if start == aes.OB_ROOT:
        origin = (0, 0)
    else:
        origin = screen_origin(image, tree, parent_by_climbing(tree, start, image))
    found, current, descended = aes.OB_NIL, start, False
    while True:
        rect = (signed(object_word(image, tree, current, "X") + origin[0]),
                signed(object_word(image, tree, current, "Y") + origin[1]),
                object_word(image, tree, current, "WIDTH"), object_word(image, tree, current, "HEIGHT"))
        hidden = object_word(image, tree, current, "FLAGS") & 1 << aes.OB_FLAG_HIDETREE_BIT
        if inside(x, y, rect) and not hidden:
            found, child = current, object_word(image, tree, current, "TAIL")
            if child == aes.OB_NIL or depth == 0:
                return found
            current, depth, origin, descended = child, depth - 1, rect[:2], True
        elif descended and found != aes.OB_NIL:
            siblings = children_of(image, tree, found)
            if siblings.index(current) == 0:
                return found
            current = siblings[siblings.index(current) - 1]
        else:
            return found


def point_in(image, tree, index, dx=0, dy=0):
    """A point `dx, dy` into object `index` of the tree on the screen."""
    x, y = screen_origin(image, tree, index)
    return x + dx, y + dy
