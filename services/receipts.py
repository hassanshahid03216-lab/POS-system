"""Best-effort receipt output: Thermal printing, PDF fallback, WhatsApp digital receipts, and Cash Drawer."""

import urllib.parse
from datetime import datetime
from pathlib import Path

from app_settings import load_settings


def _safe(text):
    return str(text).encode("latin-1", errors="replace").decode("latin-1")


def receipt_text(receipt):
    settings = load_settings()
    shop = settings.get("shop_name", "ShopFlow POS")
    phone = settings.get("shop_phone", "")
    address = settings.get("shop_address", "")
    footer = settings.get("receipt_footer", "Thank you for shopping with us!")
    currency = settings.get("currency", "Rs")

    width = 32
    lines = [shop.center(width)]
    if address:
        lines.append(address.center(width))
    if phone:
        lines.append(f"Tel: {phone}".center(width))
    lines.append("=" * width)
    
    is_return = receipt.get("is_return", False)
    closing = receipt.get("closing_summary")
    if closing:
        lines.append("DAY END CASH CLOSING".center(width))
        lines.append(f"Cashier: {_safe(closing['shift']['cashier_name'])}")
        lines.append(f"Time: {closing['timestamp']}")
        lines.append("-" * width)
        lines.append(f"Opening float: {float(closing['shift']['opening']):.2f}")
        lines.append(f"Cash sales: {closing['cash_sales']:.2f}")
        lines.append(f"Khata recoveries: {closing['khata_recoveries']:.2f}")
        lines.append(f"Cash refunds: -{closing['cash_refunds']:.2f}")
        lines.append(f"Petty expenses: -{closing['expenses']:.2f}")
        lines.append(f"Expected cash: {closing['expected']:.2f}")
        lines.append(f"Counted cash: {closing['actual']:.2f}")
        lines.append(f"Variance: {closing['variance']:+.2f}")
        lines.append("=" * width)
        lines.extend(("", ""))
        return "\n".join(_safe(line) for line in lines)
    if is_return:
        lines.append("SALE RETURN / REFUND".center(width))
        lines.append(f"Ref Sale #{receipt.get('sale_id', '')}")
    else:
        lines.append(f"Receipt #{receipt.get('sale_id', '')}")
        
    lines.append(receipt.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if receipt.get("customer_name"):
        lines.append(f"Customer: {receipt['customer_name']}")
    lines.append("-" * width)

    for item in receipt.get("items", []):
        qty = int(item["qty"])
        unit = float(item["unit_price"])
        discount = float(item.get("discount", 0))
        lines.append(_safe(item["name"])[:width])
        lines.append(f"{qty} x {unit:.2f}  {qty * unit - discount:.2f}")
        if discount:
            lines.append(f"  Item discount: -{discount:.2f}")

    lines.append("-" * width)
    if not is_return:
        lines.append(f"Subtotal: {currency} {float(receipt.get('subtotal', 0)):.2f}")
        if float(receipt.get("discount", 0)) > 0:
            lines.append(f"Discount: {currency} {float(receipt.get('discount', 0)):.2f}")
        lines.append(f"TOTAL: {currency} {float(receipt.get('total', 0)):.2f}")
        if float(receipt.get("voucher_credit", 0)) > 0:
            lines.append(f"Voucher credit: -{currency} {float(receipt['voucher_credit']):.2f}")
            if receipt.get("voucher_code"):
                lines.append(f"Voucher: {receipt['voucher_code']}")
            lines.append(f"Amount Due: {currency} {float(receipt.get('amount_due', receipt.get('total', 0) - receipt.get('voucher_credit', 0))):.2f}")
        lines.append(f"Payment: {receipt.get('payment_mode', 'Cash')}")
        if float(receipt.get("tendered", 0)) > 0:
            lines.append(f"Cash Tendered: {currency} {float(receipt.get('tendered', 0)):.2f}")
            lines.append(f"Change Return: {currency} {float(receipt.get('change', 0)):.2f}")
    else:
        if receipt.get("refund_method"):
            lines.append(f"Method: {receipt['refund_method']}")
        if receipt.get("voucher_code"):
            lines.append(f"Voucher: {receipt['voucher_code']}")
        lines.append(f"TOTAL REFUND: {currency} {float(receipt.get('refund_amount', 0)):.2f}")

    lines.append("=" * width)
    for fline in footer.splitlines():
        if fline.strip():
            lines.append(_safe(fline.strip()).center(width))
    lines.extend(("", ""))
    return "\n".join(_safe(line) for line in lines)


def generate_whatsapp_text(receipt):
    """Generate a clean, beautiful Markdown receipt for WhatsApp sharing."""
    settings = load_settings()
    shop = settings.get("shop_name", "ShopFlow POS")
    currency = settings.get("currency", "Rs")
    phone = settings.get("shop_phone", "")
    
    is_return = receipt.get("is_return", False)
    header_title = f"🔄 *{shop} - Sale Return*" if is_return else f"🧾 *{shop} - Bill Receipt*"
    
    lines = [
        header_title,
        f"📅 Date: {receipt.get('timestamp') or datetime.now().strftime('%d-%b-%Y %I:%M %p')}",
        f"🆔 Bill #{receipt.get('sale_id', '')}",
    ]
    if receipt.get("customer_name"):
        lines.append(f"👤 Customer: {receipt['customer_name']}")
    lines.append("--------------------------------")
    
    for item in receipt.get("items", []):
        qty = item["qty"]
        unit = float(item["unit_price"])
        item_total = qty * unit - float(item.get("discount", 0))
        lines.append(f"• *{item['name']}*\n   {qty} x {currency} {unit:.2f} = *{currency} {item_total:.2f}*")
    
    lines.append("--------------------------------")
    if not is_return:
        if float(receipt.get("discount", 0)) > 0:
            lines.append(f"🏷️ Discount: {currency} {float(receipt.get('discount', 0)):.2f}")
        lines.append(f"💰 *Total Amount: {currency} {float(receipt.get('total', 0)):.2f}*")
        lines.append(f"💳 Payment Mode: *{receipt.get('payment_mode', 'Cash')}*")
        if float(receipt.get("voucher_credit", 0)) > 0:
            lines.append(f"Voucher credit: -{currency} {float(receipt['voucher_credit']):.2f}")
            lines.append(f"Amount due: {currency} {float(receipt.get('amount_due', 0)):.2f}")
        if float(receipt.get("change", 0)) > 0:
            lines.append(f"💵 Change Given: {currency} {float(receipt.get('change', 0)):.2f}")
    else:
        lines.append(f"💸 *Refunded Amount: {currency} {float(receipt.get('refund_amount', 0)):.2f}*")
        
    lines.append("--------------------------------")
    lines.append("🙏 *Thank you for shopping with us!*")
    if phone:
        lines.append(f"📞 Contact: {phone}")
    return "\n".join(lines)


def generate_whatsapp_url(receipt, phone_number="", include_full_text=True, caption=None):
    """Generate a https://wa.me/ URL with pre-filled message text."""
    if include_full_text:
        text = generate_whatsapp_text(receipt)
    else:
        settings = load_settings()
        shop = settings.get("shop_name", "ShopFlow POS")
        sale_id = receipt.get("sale_id", "")
        total = float(receipt.get("total", 0))
        currency = settings.get("currency", "Rs")
        is_return = receipt.get("is_return", False)
        if caption is not None:
            text = caption
        elif is_return:
            text = f"Assalam-o-Alaikum! *{shop}* se Return/Refund Receipt #{sale_id} hazir hai."
        else:
            text = f"Assalam-o-Alaikum! *{shop}* se aapka Bill #{sale_id} (Total: {currency} {total:,.2f}) hazir hai."

    clean_phone = "".join(ch for ch in str(phone_number) if ch.isdigit())
    if clean_phone.startswith("03"):
        clean_phone = "92" + clean_phone[1:]

    if text:
        encoded_text = urllib.parse.quote(text)
        if clean_phone:
            return f"https://wa.me/{clean_phone}?text={encoded_text}"
        return f"https://wa.me/?text={encoded_text}"
    else:
        if clean_phone:
            return f"https://wa.me/{clean_phone}"
        return "https://web.whatsapp.com"


def available_printers():
    """Return installed Windows printer names."""
    try:
        from escpos.printer import Win32Raw
        printer = Win32Raw()
        return sorted(printer.printers.keys())
    except Exception:
        return []


def test_printer(printer_name):
    if not printer_name:
        raise ValueError("Select a printer first.")
    from escpos.printer import Win32Raw
    printer = Win32Raw(printer_name=printer_name)
    if printer_name not in printer.printers:
        raise RuntimeError("The selected printer is not currently available.")
    printer.open(job_name="ShopFlow printer test")
    try:
        printer.set(align="center", bold=True)
        printer.text("ShopFlow POS\nPrinter test OK\n\n")
        printer.cut()
    finally:
        printer.close()
    return "Test receipt sent."


def kick_cash_drawer(printer_name=None):
    """Send standard ESC/POS pulse command to open the cash drawer."""
    if not printer_name:
        printer_name = load_settings().get("printer_name", "")
    if not printer_name:
        return False
    try:
        from escpos.printer import Win32Raw
        printer = Win32Raw(printer_name=printer_name)
        printer.open(job_name="Open Drawer")
        try:
            printer._raw(b"\x1b\x70\x00\x19\xfa")
            printer._raw(b"\x1b\x70\x01\x19\xfa")
        finally:
            printer.close()
        return True
    except Exception:
        return False


def _print_escpos(receipt, printer_name):
    from escpos.printer import Win32Raw
    printer = Win32Raw(printer_name=printer_name)
    if printer_name not in printer.printers:
        raise RuntimeError("Selected thermal printer is not detected.")
    printer.open(job_name=f"ShopFlow receipt {receipt.get('sale_id', '')}")
    try:
        printer.set(align="center", bold=True)
        printer.text(_safe(load_settings().get("shop_name", "ShopFlow POS")) + "\n")
        printer.set(align="left", bold=False)
        body = receipt_text(receipt).split("\n", 1)[1]
        printer.text(body + "\n")
        # Open cash drawer automatically on sale (sent before cut so buffer executes)
        try:
            printer._raw(b"\x1b\x70\x00\x19\xfa")
            printer._raw(b"\x1b\x70\x01\x19\xfa")
        except Exception:
            pass
        printer.cut()
    finally:
        printer.close()


def _save_pdf(receipt):
    from fpdf import FPDF

    folder = Path.home() / "Documents" / "ShopFlow POS" / "Receipts"
    folder.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = folder / f"receipt_{receipt.get('sale_id', 'sale')}_{timestamp}.pdf"
    lines = receipt_text(receipt).splitlines()
    height = max(135, 28 + len(lines) * 5)
    pdf = FPDF(unit="mm", format=(80, height))
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    pdf.set_font("helvetica", size=9)
    for index, line in enumerate(lines):
        if index in (0,):
            pdf.set_font("helvetica", style="B", size=12)
        elif line.startswith("TOTAL"):
            pdf.set_font("helvetica", style="B", size=11)
        else:
            pdf.set_font("helvetica", size=9)
        pdf.cell(0, 5, _safe(line)[:45], new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))
    return str(path)


def print_or_save_receipt(receipt):
    """Try the configured printer; save a PDF on absent or failed printing."""
    printer_name = load_settings().get("printer_name", "")
    failure = None
    if printer_name:
        try:
            _print_escpos(receipt, printer_name)
            return {"kind": "printed", "message": "Receipt printed and drawer opened."}
        except Exception as error:
            failure = str(error)
    else:
        failure = "No printer is configured."
    try:
        path = _save_pdf(receipt)
        return {"kind": "pdf", "path": path, "message": f"Receipt saved as PDF: {path}", "printer_error": failure}
    except Exception as error:
        return {"kind": "error", "message": f"Sale is complete, but receipt output failed: {error}", "printer_error": failure}
