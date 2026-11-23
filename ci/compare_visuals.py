#!/usr/bin/env python3
"""Standalone Android TV screenshot visual review. Actual pixels only; no synthetic app screenshot."""
from PIL import Image, ImageChops, ImageEnhance, ImageDraw, ImageFont
from pathlib import Path
from io import BytesIO
import base64, json, numpy as np

out = Path("report")
out.mkdir(exist_ok=True)
reference = Image.open(out / "reference.png").convert("RGB")
actual = Image.open(out / "actual-popup-right.png").convert("RGB")
actual_size = actual.size
if actual.size != reference.size:
    actual = actual.resize(reference.size, Image.Resampling.LANCZOS)
    dimensions_note = f"Emulator capture {actual_size}, reference {reference.size}; resized for comparison"
else:
    dimensions_note = f"Same dimensions: {reference.size}"
a = np.asarray(reference).astype(np.int16)
b = np.asarray(actual).astype(np.int16)
d = np.abs(a - b)
exact = float(np.all(d == 0, axis=2).mean() * 100)
within20 = float(np.all(d <= 20, axis=2).mean() * 100)
mae = float(np.mean(d))
max_diff = np.max(d,axis=2).astype(np.uint8)

difference = ImageEnhance.Contrast(ImageChops.difference(reference, actual)).enhance(2)
difference.save(out / "difference-heatmap.png")
Image.blend(reference, actual, 0.5).save(out / "50-50-overlay.png")
# Deterministic, literal full screenshot comparison: no attempt to fake a screenshot.
w,h = reference.size
side = Image.new("RGB",(w*2,h+56),(9,16,26))
side.paste(reference,(0,56))
side.paste(actual,(w,56))
draw = ImageDraw.Draw(side)
draw.text((24,20),"APPROVED DESIGN REFERENCE",fill=(250,250,250))
draw.text((w+24,20),"ACTUAL ANDROID TV EMULATOR SCREENSHOT",fill=(250,250,250))
side.save(out / "reference-vs-actual.png")
metrics = {
    "reference_size": list(reference.size), "actual_size": list(actual_size),
    "exact_rgb_pixel_match_percent": round(exact,3),
    "pixels_within_20_each_channel_percent": round(within20,3),
    "mean_absolute_channel_difference_0_to_255": round(mae,3),
    "note": "Reference includes fictional inventory, while emulator has synthetic real files; these scores are a diagnostic baseline and not a fair final parity pass/fail."
}
(out/"metrics.json").write_text(json.dumps(metrics,indent=2))
for image, label in [(reference,"reference"),(actual,"actual"),(difference,"difference")]:
    buff=BytesIO();image.save(buff,format="PNG")
    metrics[label+"_b64"] = base64.b64encode(buff.getvalue()).decode("ascii")
html = """<!doctype html><meta charset="utf-8"><title>TV Sync visual parity</title>
<style>body{background:#070e17;color:#f4f7fa;font:16px system-ui;margin:0;padding:28px}main{max-width:1600px;margin:auto}
p{color:#c9d5e2}h1{font-size:28px} .compare{position:relative;width:100%;aspect-ratio:1672/941;overflow:hidden;border:1px solid #27d9df;border-radius:12px}
.compare img{width:100%;height:100%;position:absolute;inset:0;object-fit:cover}
#actual{clip-path:inset(0 50% 0 0)}#bar{position:absolute;top:0;bottom:0;left:50%;width:2px;background:#fff;pointer-events:none}
input{width:100%;accent-color:#0fe6ee} .pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}.pair img{width:100%}
code{color:#38edee}@media(max-width:700px){.pair{display:block}}</style>
<main><h1>TV Sync — reference versus real Android TV screenshot</h1>
<p>Move the slider to reveal the actual emulator pixels over the approved mockup. Screenshot comparisons are NOT proof of functional or performance parity.</p>
<div class="compare"><img src="data:image/png;base64,REFERENCE"><img id="actual" src="data:image/png;base64,ACTUAL"><span id="bar"></span></div>
<input type="range" id="blend" min="0" max="100" value="50" aria-label="Comparison slider">
<p><strong>Exact RGB match:</strong> EXACT% · <strong>Within ±20 per channel:</strong> WITHIN% · <strong>Mean difference:</strong> MAE/255</p>
<p>These values include different filenames and test data; use as a baseline only. Real-device parity and fluid animation remain unverified.</p>
<div class="pair"><div><h2>Approved design</h2><img src="data:image/png;base64,REFERENCE"></div><div><h2>Difference heatmap</h2><img src="data:image/png;base64,DIFF"></div></div>
</main><script>const input=document.querySelector('#blend'),actual=document.querySelector('#actual'),bar=document.querySelector('#bar');input.addEventListener('input',()=>{const p=input.value;actual.style.clipPath='inset(0 '+(100-p)+'% 0 0)';bar.style.left=p+'%'})</script>"""
for key,value in {
  "REFERENCE":metrics["reference_b64"],"ACTUAL":metrics["actual_b64"],"DIFF":metrics["difference_b64"],
  "EXACT":f"{exact:.2f}", "WITHIN":f"{within20:.2f}", "MAE":f"{mae:.2f}"
}.items():html=html.replace(key,value)
(out/"interactive-comparison.html").write_text(html)
print(json.dumps({**{k:v for k,v in metrics.items() if not k.endswith("_b64")}},indent=2))
