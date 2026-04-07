"""
Panel tester — live visual preview for the case file card.

Run with:
    streamlit run tools/panel_tester.py
"""

import io
import sys
import textwrap
import os
from pathlib import Path

import streamlit as st
from PIL import Image, ImageDraw, ImageFont

# Make forge importable from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from forge.composer import _NICHE_PANEL_STYLES, _FONT_DIR

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Panel Tester", layout="centered")
st.title("Case Panel Tester")

# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------

col_left, col_right = st.columns([1, 1])

with col_left:
    niche = st.selectbox("Niche", list(_NICHE_PANEL_STYLES.keys()))
    hook  = st.text_area(
        "Hook text",
        value="She vanished in 1987 and has never been found.",
        height=100,
    )
    subreddit = st.text_input("Subreddit", value="UnresolvedMysteries")
    badge_override = st.text_input("Badge label (override)", value="")

with col_right:
    st.caption("Card style")
    style = _NICHE_PANEL_STYLES[niche].copy()

    badge_r, badge_g, badge_b = style["badge_color"][:3]
    badge_hex = "#{:02x}{:02x}{:02x}".format(badge_r, badge_g, badge_b)
    badge_hex = st.color_picker("Badge colour", badge_hex)
    br, bg, bb = int(badge_hex[1:3], 16), int(badge_hex[3:5], 16), int(badge_hex[5:7], 16)
    style["badge_color"] = (br, bg, bb, 255)

    card_r, card_g, card_b = style["card_fill"][:3]
    card_hex = "#{:02x}{:02x}{:02x}".format(card_r, card_g, card_b)
    card_hex = st.color_picker("Card background", card_hex)
    cr, cg, cb = int(card_hex[1:3], 16), int(card_hex[3:5], 16), int(card_hex[5:7], 16)
    style["card_fill"] = (cr, cg, cb, 245)

    outline_r, outline_g, outline_b = style["card_outline"][:3]
    outline_hex = "#{:02x}{:02x}{:02x}".format(outline_r, outline_g, outline_b)
    outline_hex = st.color_picker("Card outline", outline_hex)
    or_, og, ob = int(outline_hex[1:3], 16), int(outline_hex[3:5], 16), int(outline_hex[5:7], 16)
    style["card_outline"] = (or_, og, ob, 200)

    badge_size  = st.slider("Badge font size", 18, 60, 30)
    title_size  = st.slider("Title font size", 28, 80, 52)
    sub_size    = st.slider("Subreddit font size", 18, 60, 32)
    card_width_pct = st.slider("Card width %", 60, 98, 92)
    card_top_pct   = st.slider("Card vertical position %", 20, 70, 38)

# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

WIDTH, HEIGHT = 540, 960   # half-res preview (same aspect as 1080x1920)

def render_preview(hook, subreddit, style, badge_override,
                   badge_size, title_size, sub_size,
                   card_width_pct, card_top_pct) -> Image.Image:
    pad    = 20
    card_w = int(WIDTH * card_width_pct / 100)

    def load_font(name, size):
        try:
            return ImageFont.truetype(os.path.join(_FONT_DIR, name), size)
        except Exception:
            return ImageFont.load_default()

    font_badge = load_font("segoeuib.ttf", badge_size)
    font_title = load_font("segoeuib.ttf", title_size)
    font_sub   = load_font("segoeuib.ttf", sub_size)

    badge_label = badge_override.strip() or style["badge"]
    wrapped = textwrap.wrap(hook, width=26)[:4]
    line_h  = title_size + 12
    card_h  = pad * 2 + badge_size + 20 + 2 + 20 + len(wrapped) * line_h + 20 + sub_size + 16

    card_top = int(HEIGHT * card_top_pct / 100)

    # Dark background so the transparent card is visible
    bg   = Image.new("RGBA", (WIDTH, HEIGHT), (20, 20, 28, 255))
    img  = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    x0 = (WIDTH - card_w) // 2
    x1 = x0 + card_w
    y0 = card_top
    y1 = card_top + card_h

    draw.rounded_rectangle([x0, y0, x1, y1], radius=10, fill=style["card_fill"])
    draw.rounded_rectangle([x0, y0, x1, y1], radius=10, outline=style["card_outline"], width=2)

    y = y0 + pad
    draw.text((x0 + pad, y), badge_label, font=font_badge, fill=style["badge_color"])
    y += badge_size + 10
    draw.line([(x0 + pad, y + 5), (x1 - pad, y + 5)], fill=style["divider"], width=1)
    y += 18

    for line in wrapped:
        draw.text((x0 + pad, y), line, font=font_title, fill=(255, 255, 255, 255))
        y += line_h

    y += 16
    draw.text((x0 + pad, y), f"r/{subreddit}", font=font_sub, fill=(255, 69, 0, 255))

    return Image.alpha_composite(bg, img)


preview = render_preview(
    hook, subreddit, style, badge_override,
    badge_size, title_size, sub_size,
    card_width_pct, card_top_pct,
)

st.image(preview, caption="Preview (540×960 — same aspect as 1080×1920)", use_container_width=True)

# ---------------------------------------------------------------------------
# Export config snippet
# ---------------------------------------------------------------------------

with st.expander("Copy style values to composer.py"):
    st.code(f"""
    "{niche}": {{
        "badge":        "{badge_override.strip() or _NICHE_PANEL_STYLES[niche]['badge']}",
        "badge_color":  {style['badge_color']},
        "card_fill":    {style['card_fill']},
        "card_outline": {style['card_outline']},
        "divider":      {style['divider']},
    }},
""", language="python")
