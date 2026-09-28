"""Round 14 barcode design helper: builds the per-frame index barcode filter
chain (encode side) and the crop/signalstats decode graph (probe side).

No expression here uses a comma: PATTERN_GRAPH is carried through mpv's
av://lavfi: URL (capture_diagnostic.py's own comment notes a comma inside an
option's expression is the risk there, not a top-level filter-chain comma).
Every bit and the parity bit are extracted with the floor-difference identity
already used by the existing level pattern (3*n-7*floor(3*n/7)-3), never
mod(), so nothing here depends on whether that URL layer forwards a quoted
comma correctly -- mpv/ffmpeg's own filter-chain commas (separating drawbox
from drawbox) are unaffected; only literal commas one level in, mid-value.
"""
import sys

WIDTH, HEIGHT = 1024, 768
FPS = 60
INDEX_BITS = 14
CELL = 32          # full tile size (tiling, no gaps)
INSET = 6          # crop inset for decode (avoid block-edge bleed)
N_CELLS = INDEX_BITS + 1  # + parity

def _bit_expr(k):
    # floor(n/2^k) - 2*floor(n/2^(k+1))  ==  floor(n/2^k) mod 2, no comma.
    return f"(floor(n/{2**k})-2*floor(n/{2**(k+1)}))"

def _parity_expr():
    total = "+".join(_bit_expr(k) for k in range(INDEX_BITS))
    # sum mod 2 via the same floor-difference identity, still no comma.
    return f"(({total})-2*floor(({total})/2))"

def region_filters(y0):
    out = []
    for cell in range(N_CELLS):
        x0 = cell * CELL
        expr = _bit_expr(cell) if cell < INDEX_BITS else _parity_expr()
        out.append(f"drawbox=x={x0}:y={y0}:w={CELL}:h={CELL}:color=black:t=fill")
        out.append(f"drawbox=x={x0}:y={y0}:w={CELL}:h={CELL}:color=white:t=fill:enable='{expr}'")
    return out

def pattern_step():
    return "eq=contrast=0.4:brightness=(3*n-7*floor(3*n/7)-3)*0.02:eval=frame"

def barcode_filters():
    return region_filters(0) + region_filters(HEIGHT - CELL)

def encode_graph(duration_s):
    filters = [f"testsrc2=size={WIDTH}x{HEIGHT}:rate={FPS}:duration={duration_s}", pattern_step()]
    filters += barcode_filters()
    return ",".join(filters)

def cell_crop_labels():
    labels = []
    for region, y0 in (("top", 0), ("bottom", HEIGHT - CELL)):
        for cell in range(N_CELLS):
            x0 = cell * CELL
            labels.append((f"{region}{cell}", x0 + INSET, y0 + INSET, CELL - 2 * INSET, CELL - 2 * INSET))
    return labels

if __name__ == "__main__":
    print(encode_graph(float(sys.argv[1]) if len(sys.argv) > 1 else 2.0))
