"""Image receipt generator for ShopFlow POS.

Generates a beautiful PNG receipt image that can be directly shared on
WhatsApp or saved to the user's Documents folder.

Dependencies: Pillow (already installed via requirements.txt)
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app_settings import load_settings

# ── Font helpers ──────────────────────────────────────────────────────────────
_FONT_DIR = "C:/Windows/Fonts"


def _font(style: str, size: int) -> ImageFont.FreeTypeFont:
    candidates = {
        "regular": ["segoeui.ttf",  "arial.ttf",     "DejaVuSans.ttf"],
        "bold":    ["segoeuib.ttf", "arialbd.ttf",   "DejaVuSans-Bold.ttf"],
        "light":   ["segoeuil.ttf", "segoeui.ttf",   "arial.ttf"],
        "mono":    ["consola.ttf",  "cour.ttf",       "DejaVuSansMono.ttf"],
    }.get(style, ["arial.ttf"])
    for name in candidates:
        path = os.path.join(_FONT_DIR, name)
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ── Palette ───────────────────────────────────────────────────────────────────
BG       = (15,  23,  42)
CARD     = (30,  41,  59)
ACCENT   = (56, 189, 248)
GREEN    = (74, 222, 128)
MUTED    = (100, 116, 139)
TEXT     = (226, 232, 240)
TEXT_DIM = (148, 163, 184)
DIVIDER  = (51,  65,  85)
RED      = (248, 113, 113)
AMBER    = (251, 191,  36)
WHITE    = (255, 255, 255)
DEEP_BL  = (12,  74, 110)


def _tw(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def generate_receipt_image(receipt: dict) -> str:
    """Render a dark-themed PNG receipt and return its saved file path."""
    s         = load_settings()
    shop_name = s.get("shop_name", "ShopFlow POS")
    shop_addr = s.get("shop_address", "")
    shop_tel  = s.get("shop_phone", "")
    footer    = s.get("receipt_footer", "Thank you for shopping with us!")
    currency  = s.get("currency", "Rs")

    is_return = receipt.get("is_return", False)
    items     = receipt.get("items", [])
    timestamp = receipt.get("timestamp") or datetime.now().strftime("%d %b %Y  %I:%M %p")
    sale_id   = receipt.get("sale_id", "")
    customer  = receipt.get("customer_name", "")
    total     = float(receipt.get("total", 0))
    discount  = float(receipt.get("discount", 0))
    subtotal  = float(receipt.get("subtotal", total))
    payment   = receipt.get("payment_mode", "Cash")
    tendered  = float(receipt.get("tendered", 0))
    change    = float(receipt.get("change", 0))
    refund    = float(receipt.get("refund_amount", 0))

    # ── Fonts ─────────────────────────────────────────────────────────────────
    f_shop   = _font("bold",    30)
    f_addr   = _font("light",   14)
    f_head   = _font("bold",    16)
    f_label  = _font("regular", 14)
    f_val    = _font("bold",    14)
    f_item   = _font("regular", 13)
    f_item_b = _font("bold",    13)
    f_total  = _font("bold",    24)
    f_small  = _font("light",   12)
    f_footer = _font("light",   13)
    f_badge  = _font("bold",    11)

    W   = 520
    PAD = 28
    RH  = 36    # row height
    IH  = 54    # item row height

    # ── Height estimation ─────────────────────────────────────────────────────
    hdr_h  = 148
    meta_n = 3 + (1 if customer else 0)
    meta_h = meta_n * RH + 20
    itm_h  = IH * len(items) + 20
    sum_n  = 2 + (1 if discount > 0 else 0) + (2 if tendered > 0 else 0)
    sum_h  = sum_n * RH + 80  # +80 for total box
    ftr_h  = 80
    H = hdr_h + meta_h + itm_h + sum_h + ftr_h + 20

    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # ══════════════════════════════════════════════════════════════════════════
    # HEADER
    # ══════════════════════════════════════════════════════════════════════════
    draw.rectangle([0, 0, W, hdr_h], fill=CARD)
    draw.rectangle([0, 0, W, 5], fill=ACCENT)        # top accent stripe

    sw = _tw(draw, shop_name, f_shop)
    draw.text(((W - sw) // 2, 18), shop_name, font=f_shop, fill=ACCENT)

    y = 58
    for detail, col in [(shop_addr, TEXT_DIM), (f"Tel: {shop_tel}" if shop_tel else "", TEXT_DIM)]:
        if detail:
            dw = _tw(draw, detail, f_addr)
            draw.text(((W - dw) // 2, y), detail, font=f_addr, fill=col)
            y += 20

    # Badge
    badge_txt   = "SALE RETURN" if is_return else "SALE RECEIPT"
    badge_color = RED if is_return else GREEN
    bw = _tw(draw, badge_txt, f_badge) + 24
    bx = (W - bw) // 2
    draw.rounded_rectangle((bx, y + 4, bx + bw, y + 22), radius=6, fill=badge_color)
    draw.text((bx + 12, y + 5), badge_txt, font=f_badge, fill=WHITE)

    y = hdr_h + 14

    # ══════════════════════════════════════════════════════════════════════════
    # META ROWS
    # ══════════════════════════════════════════════════════════════════════════
    def meta_row(label, value, vc=TEXT):
        nonlocal y
        draw.text((PAD, y), label, font=f_label, fill=MUTED)
        vw = _tw(draw, value, f_val)
        draw.text((W - PAD - vw, y), value, font=f_val, fill=vc)
        y += RH

    meta_row("Bill #",   f"#{sale_id}",  ACCENT)
    meta_row("Date",     timestamp,       TEXT)
    meta_row("Payment",  payment,         GREEN if not is_return else RED)
    if customer:
        meta_row("Customer", customer, AMBER)

    draw.rectangle([PAD, y, W - PAD, y + 2], fill=DIVIDER)
    y += 12

    # ══════════════════════════════════════════════════════════════════════════
    # ITEMS
    # ══════════════════════════════════════════════════════════════════════════
    draw.text((PAD, y), "ITEM", font=f_badge, fill=MUTED)
    draw.text((W - PAD - _tw(draw, "AMOUNT", f_badge), y), "AMOUNT", font=f_badge, fill=MUTED)
    y += 18

    for item in items:
        qty   = int(item.get("qty", 1))
        unit  = float(item.get("unit_price", 0))
        disc  = float(item.get("discount", 0))
        ltot  = qty * unit - disc
        name  = str(item.get("name", ""))
        name  = (name[:30] + "…") if len(name) > 30 else name

        draw.text((PAD, y), name, font=f_item_b, fill=TEXT)
        amt = f"{currency} {ltot:,.2f}"
        draw.text((W - PAD - _tw(draw, amt, f_val), y), amt, font=f_val, fill=TEXT)
        y += 20

        sub = f"  {qty} x {currency} {unit:,.2f}"
        if disc > 0:
            sub += f"  (disc: -{currency} {disc:,.2f})"
        draw.text((PAD, y), sub, font=f_small, fill=MUTED)
        y += 22
        draw.rectangle([PAD, y - 3, W - PAD, y - 2], fill=DIVIDER)

    y += 8
    draw.rectangle([PAD, y, W - PAD, y + 2], fill=ACCENT)
    y += 14

    # ══════════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════════════════
    def sum_row(label, value, lc=TEXT_DIM, vc=TEXT, bold=False):
        nonlocal y
        draw.text((PAD, y), label, font=f_label, fill=lc)
        vf = f_val if bold else f_label
        vw = _tw(draw, value, vf)
        draw.text((W - PAD - vw, y), value, font=vf, fill=vc)
        y += RH

    if not is_return:
        sum_row("Subtotal",     f"{currency} {subtotal:,.2f}")
        if discount > 0:
            sum_row("Discount", f"- {currency} {discount:,.2f}", vc=RED)
        if tendered > 0:
            sum_row("Cash Tendered", f"{currency} {tendered:,.2f}", vc=GREEN)
            sum_row("Change Return", f"{currency} {change:,.2f}",   vc=GREEN)
    else:
        sum_row("Refunded", f"{currency} {refund:,.2f}", vc=RED, bold=True)

    y += 4
    # Total box
    box_h = 64
    draw.rounded_rectangle((PAD, y, W - PAD, y + box_h), radius=12,
                            fill=DEEP_BL, outline=ACCENT, width=2)
    lbl = "TOTAL REFUND" if is_return else "TOTAL AMOUNT"
    draw.text((PAD + 18, y + 12), lbl, font=f_head, fill=ACCENT)
    amt_str = f"{currency} {(refund if is_return else total):,.2f}"
    aw = _tw(draw, amt_str, f_total)
    draw.text((W - PAD - 18 - aw, y + 10), amt_str, font=f_total, fill=WHITE)
    y += box_h + 18

    # ══════════════════════════════════════════════════════════════════════════
    # FOOTER
    # ══════════════════════════════════════════════════════════════════════════
    draw.rectangle([PAD, y, W - PAD, y + 1], fill=DIVIDER)
    y += 14
    for fline in footer.splitlines():
        fline = fline.strip()
        if not fline:
            continue
        fw = _tw(draw, fline, f_footer)
        draw.text(((W - fw) // 2, y), fline, font=f_footer, fill=TEXT_DIM)
        y += 22
    pb = "Powered by ShopFlow POS"
    pbw = _tw(draw, pb, f_small)
    draw.text(((W - pbw) // 2, y + 4), pb, font=f_small, fill=DIVIDER)

    # ── Save PNG ──────────────────────────────────────────────────────────────
    folder = Path.home() / "Documents" / "ShopFlow POS" / "Receipts"
    folder.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = folder / f"receipt_{sale_id}_{ts}.png"
    img.save(str(path), "PNG", optimize=True)
    return str(path)


def copy_receipt_image_to_clipboard(image_path: str) -> bool:
    """Copy receipt PNG image directly to Windows OS kernel clipboard so Ctrl+V in WhatsApp works 100%."""
    success = False

    # 1. Native Windows CF_DIB (Kernel clipboard - instant & 100% reliable across all apps)
    try:
        import io
        import win32clipboard
        from PIL import Image

        pil_img = Image.open(str(image_path))
        output = io.BytesIO()
        pil_img.convert("RGB").save(output, "BMP")
        bmp_data = output.getvalue()[14:]  # Strip 14-byte BMP file header for CF_DIB
        output.close()

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, bmp_data)
        win32clipboard.CloseClipboard()
        success = True
    except Exception as e:
        print("win32clipboard error:", e)

    # 2. Also set Qt clipboard as backup
    try:
        from PySide6.QtCore import QMimeData, QUrl
        from PySide6.QtGui import QImage
        from PySide6.QtWidgets import QApplication

        img = QImage(str(image_path))
        if not img.isNull():
            mime = QMimeData()
            mime.setImageData(img)
            mime.setUrls([QUrl.fromLocalFile(str(image_path))])
            cb = QApplication.clipboard()
            if cb:
                cb.setMimeData(mime)
                success = True
    except Exception as e:
        print("Qt clipboard error:", e)

    return success
