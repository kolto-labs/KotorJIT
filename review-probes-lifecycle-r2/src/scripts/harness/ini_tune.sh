# Force the ini settings headless boot actually depends on.
#
# ini_headless <path-to-swkotor.ini>
#
# Two settings, and both were found the hard way:
#
#   EnableCheats=1   without it the console key does nothing at all.
#
#   Frame Buffer=0   the pristine default is 1, and under Xvfb + llvmpipe that
#                     renders the entire 3D world as flat black -- the HUD,
#                     minimap and portraits all draw fine, which is what made
#                     this look like a renderer-wide failure rather than one
#                     setting. Confirmed by isolation: an otherwise-identical
#                     boot through this same harness, same env-isolation, same
#                     display, differed only in this one key between a black
#                     world and a fully lit one (69k+ colours in-frame vs ~1).
#                     Root cause not fully understood -- llvmpipe presumably
#                     chokes on whatever KOTOR's framebuffer-effects pass does
#                     -- but the fix is exact and repeatable.
#
# Three call sites had each grown their own slightly different sed for the
# first setting alone before this existed; this replaces all three.
ini_headless() {
  local ini="$1"
  [[ -f "$ini" ]] || return 0
  grep -qi "EnableCheats" "$ini" || sed -i '/^\[Game Options\]/a EnableCheats=1' "$ini"
  sed -i 's/^EnableCheats=.*/EnableCheats=1/I' "$ini"
  grep -qi "^Frame Buffer=" "$ini" || sed -i '/^\[Graphics Options\]/a Frame Buffer=0' "$ini"
  sed -i 's/^Frame Buffer=.*/Frame Buffer=0/I' "$ini"
}
