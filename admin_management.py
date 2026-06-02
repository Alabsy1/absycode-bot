"""
AbsyCode Marine Bot — Admin Management CLI (Req #7)
====================================================
Run standalone:  python admin_management.py
Import anywhere: import admin_management as admin

NOTE: database.py is now fully async (aiosqlite).
      This CLI wraps all calls with asyncio.run().
"""

import sys
import os
import asyncio
from datetime import datetime

# Allow running from the project root
sys.path.insert(0, os.path.dirname(__file__))
import database


# ─────────────────────────────────────────────────────────────
# ASYNC HELPER
# ─────────────────────────────────────────────────────────────

def _run(coro):
    """Run an async coroutine from sync context."""
    return asyncio.run(coro)


# ─────────────────────────────────────────────────────────────
# API FUNCTIONS (importable)
# ─────────────────────────────────────────────────────────────

def list_all_users() -> list:
    """Returns all users with subscription and registration info."""
    return _run(database.get_all_users_stats())


def extend_subscription(user_id: int, days: int) -> str:
    """Extends (or creates) a user's subscription by `days`. Returns new expiry."""
    expiry = _run(database.add_or_update_user(user_id, days))
    _run(database.log_action(user_id, 'admin_extend', f'+{days} days. New expiry: {expiry}'))
    return expiry


def reduce_subscription(user_id: int, days: int) -> str:
    """Reduces a user's subscription by `days`. Returns new expiry."""
    expiry = _run(database.reduce_subscription(user_id, days))
    _run(database.log_action(user_id, 'admin_reduce', f'-{days} days. New expiry: {expiry}'))
    return expiry


def set_subscription_expiry(user_id: int, expiry_iso: str) -> str:
    """Sets an exact expiry date for a user."""
    expiry = _run(database.set_subscription_expiry(user_id, expiry_iso))
    _run(database.log_action(user_id, 'admin_set_expiry', f'Exact expiry set to: {expiry}'))
    return expiry


def revoke_subscription(user_id: int):
    """Immediately deactivates a user's subscription."""
    _run(database.revoke_user(user_id))
    _run(database.log_action(user_id, 'admin_revoke', 'Subscription immediately revoked'))


def set_boat_name(user_id: int, boat_name: str):
    """Updates a user's boat name."""
    _run(database.update_boat_name(user_id, boat_name))
    _run(database.log_action(user_id, 'admin_boat_name_set', f'Boat name set to: {boat_name}'))


def add_new_user(user_id: int, days: int, boat_name: str = "مركب غير مسمى") -> str:
    """Manually onboards a new user. Returns new expiry date string."""
    expiry = _run(database.add_or_update_user(user_id, days, boat_name=boat_name))
    _run(database.log_action(user_id, 'admin_add_user', f'Created with {days} days. Boat: {boat_name}'))
    return expiry


def get_user_invoice_count(user_id: int) -> int:
    """Returns how many invoices a user has saved."""
    return _run(database.count_user_invoices(user_id))


def delete_all_user_data(user_id: int) -> int:
    """Wipes all invoices for a user. Returns number deleted."""
    count = _run(database.delete_all_invoices(user_id))
    _run(database.log_action(user_id, 'admin_delete_all_invoices', f'Deleted {count} invoices'))
    return count


def get_user_audit_log(user_id: int, limit: int = 50) -> list:
    """Fetches the user's action audit log."""
    return _run(database.get_user_audit_log(user_id, limit))


# ─────────────────────────────────────────────────────────────
# DISPLAY HELPERS
# ─────────────────────────────────────────────────────────────

def _print_separator(char="─", width=60):
    print(char * width)


def _print_users_table(users: list):
    if not users:
        print("  (لا يوجد مستخدمون مسجلون)")
        return
    _print_separator()
    print(f"{'ID':>12} | {'الحالة':^8} | {'انتهاء الاشتراك':^12} | {'التسجيل':^12} | {'اسم المركب'}")
    _print_separator()
    now = datetime.now()
    for uid, boat, is_act, expiry, reg_at, _ in users:
        # Determine live status even if flag says active
        status = "❌ موقوف"
        if is_act and expiry:
            try:
                if datetime.fromisoformat(expiry) > now:
                    status = "✅ نشط"
                else:
                    status = "⏰ منتهي"
            except ValueError:
                status = "⚠️ خطأ"
        exp_str = str(expiry)[:10] if expiry else "—"
        reg_str = str(reg_at)[:10] if reg_at else "—"
        invoices = get_user_invoice_count(uid)
        print(f"{uid:>12} | {status:^8} | {exp_str:^12} | {reg_str:^12} | {boat} ({invoices} فاتورة)")
    _print_separator()
    print(f"  إجمالي المستخدمين: {len(users)}")


def _print_audit_log(logs: list):
    if not logs:
        print("  (لا توجد سجلات للمستخدم)")
        return
    _print_separator("-", 80)
    print(f"{'التاريخ والوقت':^20} | {'نوع الإجراء':^20} | {'التفاصيل'}")
    _print_separator("-", 80)
    for log_id, action_type, details, created_at in logs:
        dt_str = str(created_at)[:19].replace("T", " ")
        det = str(details or "")
        print(f"{dt_str:^20} | {action_type:^20} | {det}")
    _print_separator("-", 80)


# ─────────────────────────────────────────────────────────────
# INTERACTIVE CLI MENU
# ─────────────────────────────────────────────────────────────

def _prompt(text: str, cast=str, default=None):
    """Prompts for input with optional type casting and default."""
    try:
        raw = input(f"  {text}: ").strip()
        if not raw and default is not None:
            return default
        return cast(raw)
    except (ValueError, KeyboardInterrupt):
        return default


def menu_list_users():
    print("\n📋 قائمة جميع المستخدمين:")
    _print_users_table(list_all_users())


def menu_extend_subscription():
    print("\n➕ تمديد / تفعيل اشتراك:")
    uid  = _prompt("أدخل User ID", cast=int)
    days = _prompt("عدد الأيام", cast=int)
    if uid and days:
        new_expiry = extend_subscription(uid, days)
        print(f"  ✅ تم تفعيل {uid} حتى {new_expiry[:10]}")
    else:
        print("  ❌ إدخال غير صحيح.")


def menu_reduce_subscription():
    print("\n➖ خصم أيام من اشتراك:")
    uid  = _prompt("أدخل User ID", cast=int)
    days = _prompt("عدد الأيام للخصم", cast=int)
    if uid and days:
        new_expiry = reduce_subscription(uid, days)
        print(f"  ✅ تم خصم {days} أيام من {uid}. الانتهاء الجديد: {new_expiry[:10]}")
    else:
        print("  ❌ إدخال غير صحيح.")


def menu_set_exact_expiry():
    print("\n📅 تعيين تاريخ انتهاء محدد:")
    uid  = _prompt("أدخل User ID", cast=int)
    date_str = _prompt("تاريخ الانتهاء (YYYY-MM-DD)")
    if uid and date_str:
        try:
            iso = f"{date_str}T00:00:00"
            new_expiry = set_subscription_expiry(uid, iso)
            print(f"  ✅ تم تعيين تاريخ انتهاء {uid} إلى {new_expiry[:10]}")
        except ValueError:
            print("  ❌ صيغة التاريخ غير صحيحة.")
    else:
        print("  ❌ إدخال غير صحيح.")


def menu_revoke_subscription():
    print("\n🚫 إيقاف اشتراك:")
    uid = _prompt("أدخل User ID", cast=int)
    if uid:
        confirm = _prompt(f"هل أنت متأكد من إيقاف {uid}؟ (y/n)", default="n")
        if confirm.lower() == 'y':
            revoke_subscription(uid)
            print(f"  ✅ تم إيقاف اشتراك {uid}.")
        else:
            print("  ❌ تم الإلغاء.")


def menu_set_boat_name():
    print("\n🛥️ تغيير اسم المركب:")
    uid  = _prompt("أدخل User ID", cast=int)
    name = _prompt("الاسم الجديد للمركب")
    if uid and name:
        set_boat_name(uid, name)
        print(f"  ✅ تم تغيير اسم مركب {uid} إلى: {name}")


def menu_add_new_user():
    print("\n👤 إضافة مستخدم جديد يدوياً:")
    uid   = _prompt("User ID", cast=int)
    days  = _prompt("عدد أيام الاشتراك", cast=int, default=30)
    bname = _prompt("اسم المركب", default="مركب غير مسمى")
    if uid:
        expiry = add_new_user(uid, days, boat_name=bname)
        print(f"  ✅ تم إضافة {uid} ({bname}) حتى {expiry[:10]}")


def menu_view_user_detail():
    print("\n🔍 تفاصيل مستخدم:")
    uid = _prompt("أدخل User ID", cast=int)
    if not uid:
        return
    user = _run(database.get_user(uid))
    if not user:
        print(f"  ❌ لا يوجد مستخدم بهذا الـ ID: {uid}")
        return
    is_act, expiry, boat = user
    inv_count = get_user_invoice_count(uid)
    now = datetime.now()
    status = "❌ موقوف"
    if is_act and expiry:
        try:
            status = "✅ نشط" if datetime.fromisoformat(expiry) > now else "⏰ منتهي"
        except ValueError:
            status = "⚠️ خطأ"
    print(f"\n  👤 User ID:   {uid}")
    print(f"  🛥️ المركب:    {boat}")
    print(f"  ⏳ الحالة:    {status}")
    print(f"  📅 الانتهاء:  {str(expiry)[:10] if expiry else '—'}")
    print(f"  📄 الفواتير:  {inv_count} فاتورة مسجلة")


def menu_view_audit_log():
    print("\n📝 عرض سجل إجراءات المستخدم (Audit Log):")
    uid = _prompt("أدخل User ID", cast=int)
    if not uid:
        return
    logs = get_user_audit_log(uid, limit=50)
    _print_audit_log(logs)


def menu_delete_all_user_invoices():
    print("\n🗑️ مسح جميع فواتير مستخدم:")
    uid = _prompt("أدخل User ID", cast=int)
    if not uid:
        return
    confirm = _prompt(f"⚠️ هل أنت متأكد من مسح كل فواتير {uid}؟ (y/n)", default="n")
    if confirm.lower() == 'y':
        count = delete_all_user_data(uid)
        print(f"  ✅ تم مسح {count} فاتورة للمستخدم {uid}.")
    else:
        print("  ❌ تم الإلغاء.")


MENU_OPTIONS = [
    ("عرض جميع المستخدمين",              menu_list_users),
    ("تمديد / تفعيل اشتراك",             menu_extend_subscription),
    ("خصم أيام من اشتراك",               menu_reduce_subscription),
    ("تعيين تاريخ انتهاء محدد",          menu_set_exact_expiry),
    ("إيقاف اشتراك مستخدم",              menu_revoke_subscription),
    ("تغيير اسم مركب",                    menu_set_boat_name),
    ("إضافة مستخدم جديد يدوياً",         menu_add_new_user),
    ("عرض تفاصيل مستخدم",               menu_view_user_detail),
    ("عرض سجل الإجراءات (Audit Log)",    menu_view_audit_log),
    ("مسح جميع فواتير مستخدم",           menu_delete_all_user_invoices),
]


def run_cli():
    """Interactive admin CLI entry point."""
    _run(database.init_db())
    print("\n" + "═" * 60)
    print("   🛥️  AbsyCode Marine Bot — لوحة تحكم المشرف")
    print("═" * 60)

    while True:
        print("\n📌 الخيارات المتاحة:\n")
        for i, (label, _) in enumerate(MENU_OPTIONS, start=1):
            print(f"  {i}. {label}")
        print("  0. خروج")
        print()

        choice = _prompt("اختر رقماً", cast=int, default=0)

        if choice == 0:
            print("\n  👋 إلى اللقاء!\n")
            break
        elif 1 <= choice <= len(MENU_OPTIONS):
            try:
                MENU_OPTIONS[choice - 1][1]()
            except Exception as e:
                print(f"\n  ❌ خطأ: {e}")
        else:
            print("  ⚠️ اختيار غير صحيح، حاول مرة أخرى.")


if __name__ == "__main__":
    run_cli()
