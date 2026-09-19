# Lightweight message translation for user-facing API responses.
# Only *display* strings are translated. Never translate booleans,
# status codes or other machine-critical values.


def lang_of(request):
    if request is None:
        return "en"
    return (request.META.get("HTTP_X_LANG") or request.GET.get("lang") or "en").lower()


AR = {
    # Auth / account
    "Account created. You can now log in.": "تم إنشاء الحساب. يمكنك الآن تسجيل الدخول.",
    "Account created. Welcome to Miyar Trading!": "تم إنشاء الحساب. مرحباً بك في معيار للتداول و الإستثمار!",
    "Welcome back!": "مرحباً بعودتك!",
    "Invalid email/phone or password.": "البريد الإلكتروني أو رقم الهاتف أو كلمة المرور غير صحيحة.",
    "Your account is frozen. Contact support.": "حسابك مجمّد. يرجى التواصل مع الدعم.",
    "Your account is frozen.": "حسابك مجمّد.",
    "Your account is temporarily suspended. Try again later.": "حسابك موقوف مؤقتاً. حاول لاحقاً.",
    "Password changed successfully.": "تم تغيير كلمة المرور بنجاح.",
    "Logged out.": "تم تسجيل الخروج.",
    "Account deleted.": "تم حذف الحساب.",
    "Email address is required.": "عنوان البريد الإلكتروني مطلوب.",
    "An account with this email already exists.": "يوجد حساب مسجل بهذا البريد الإلكتروني مسبقاً.",
    "This phone number is already in use.": "رقم الهاتف هذا مستخدم بالفعل.",
    "Provide an email address or a phone number to create an account.": "يرجى تقديم بريد إلكتروني أو رقم هاتف لإنشاء الحساب.",
    "Invite code is not valid.": "رمز الدعوة غير صالح.",
    "Current password is incorrect.": "كلمة المرور الحالية غير صحيحة.",

    # Invest
    "KYC verification is required to invest.": "مطلوب التحقق من الهوية (KYC) للاستثمار.",
    "Invalid or inactive coin.": "العملة غير صالحة أو غير مفعّلة.",
    "Amount must be greater than zero.": "يجب أن يكون المبلغ أكبر من صفر.",
    "Investment created. Waiting for payment.": "تم إنشاء الاستثمار. في انتظار الدفع.",
    "Investment confirmed and balance credited.": "تم تأكيد الاستثمار وإيداع الرصيد.",
    "Minimum investment for {symbol} is {min}.": "الحد الأدنى للاستثمار في {symbol} هو {min}.",

    # Withdraw
    "KYC verification is required to withdraw.": "مطلوب التحقق من الهوية (KYC) للسحب.",
    "Minimum withdrawal is {min} {symbol}.": "الحد الأدنى للسحب هو {min} {symbol}.",
    "You must wait {hours}h between withdrawals.": "يجب الانتظار {hours} ساعة بين كل سحبتين.",
    "Amount is below the network fee threshold.": "المبلغ أقل من حد رسوم الشبكة.",
    "Insufficient withdrawable balance.": "الرصيد القابل للسحب غير كافٍ.",
    "Withdrawal request created and is pending approval. Funds are reserved and will be sent to your address once approved.": "تم إنشاء طلب السحب وهو بانتظار الموافقة. سيتم خصم المبلغ من رصيدك وإرساله إلى عنوانك بعد الموافقة.",

    # KYC
    "KYC documents submitted for review.": "تم إرسال وثائق التحقق من الهوية للمراجعة.",
    "Your account is already verified.": "حسابك موثق بالفعل.",
    "You already have a pending KYC review.": "لديك بالفعل طلب تحقق بانتظار المراجعة.",
    "Document front image is required.": "صورة الواجهة الأمامية للوثيقة مطلوبة.",
    "First name is required.": "الاسم الأول مطلوب.",
    "Last name is required.": "الاسم الأخير مطلوب.",

    # Payout windows
    "Payout not found.": "الدفعة غير موجودة.",
    "Window not found.": "نافذة الدفعة غير موجودة.",
    "Claimed successfully.": "تم المطالبة بنجاح.",

    # Notifications
    "You have a new notification.": "لديك إشعار جديد.",
    "No notifications yet.": "لا توجد إشعارات بعد.",
    "Marked as read.": "تم وضع علامة كمقروء.",
}


def tr(text, request=None, **kwargs):
    """Translate a display string based on the request language."""
    lang = lang_of(request)
    if lang.startswith("ar"):
        translated = AR.get(str(text))
        if translated:
            text = translated
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text