# Lightweight message translation for user-facing API responses.
# Only *display* strings are translated. Never translate booleans,
# status codes or other machine-critical values.

import re


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
    "Payment order not found.": "طلب الدفع غير موجود.",
    "Payment received. Your investment is confirmed and your balance is updated.": "تم استلام الدفعة. تم تأكيد استثمارك وتحديث رصيدك.",
    "Payment failed or expired.": "فشلت الدفعة أو انتهت صلاحيتها.",
    "Waiting for your payment.": "في انتظار دفعتك.",

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
    "'{title}' created.": "تم إنشاء '{title}'.",
    "'{title}' updated.": "تم تحديث '{title}'.",
    "'{title}' closed.": "تم إغلاق '{title}'.",
    "'{title}' opened ({scope}) until {until}.": "تم فتح '{title}' ({scope}) حتى {until}.",
    "Invalid percent.": "النسبة المئوية غير صالحة.",

    # Notifications
    "You have a new notification.": "لديك إشعار جديد.",
    "No notifications yet.": "لا توجد إشعارات بعد.",
    "Marked as read.": "تم وضع علامة كمقروء.",
    "Announcement sent.": "تم إرسال الإعلان.",
    "title is required.": "عنوان الإشعار مطلوب.",

    # Wallets / coins
    "Wallet not found.": "المحفظة غير موجودة.",
    "Wallet address is required.": "عنوان المحفظة مطلوب.",
    "Invalid wallet coin.": "عملة المحفظة غير صالحة.",
    "Choose a valid coin.": "يرجى اختيار عملة صالحة.",
    "Cannot delete this coin because it has investments.": "لا يمكن حذف هذه العملة لوجود استثمارات عليها.",
    "Unsupported withdrawal network {net}.": "شبكة السحب {net} غير مدعومة.",
    "Invalid {net} address. It must be a 0x… address (42 characters).": "عنوان {net} غير صالح. يجب أن يكون عنواناً يبدأ بـ 0x بطول 42 حرفاً.",
    "Invalid TRON (TRC20) address. It must start with 'T' and be 34 characters.": "عنوان TRON (TRC20) غير صالح. يجب أن يبدأ بحرف 'T' وأن يتكوّن من 34 حرفاً.",

    # Payment gateway / settings
    "Payment order not found.": "طلب الدفع غير موجود.",
    "This order is already processed.": "تمت معالجة هذا الطلب مسبقاً.",
    "This payment was already confirmed.": "تم تأكيد هذه الدفعة مسبقاً.",
    "Order {ref} marked paid and investment confirmed.": "تم تحديد الطلب {ref} كمدفوع وتم تأكيد الاستثمار.",
    "Investment order created. Complete the crypto payment to confirm it.": "تم إنشاء طلب الاستثمار. يُرجى إتمام الدفع بالعملات الرقمية لتأكيده.",
    "Investment submitted. Awaiting payment and admin confirmation.": "تم إرسال طلب الاستثمار. في انتظار الدفع وتأكيد الإدارة.",
    "The withdrawal could not be sent and your balance was refunded. Our payment provider is temporarily unable to process this network. Please try again shortly or contact support.": "تعذّر إرسال السحب وتم ردّ رصيدك بالكامل. مزوّد الدفع لدينا لا يستطيع معالجة هذه الشبكة حالياً. يُرجى المحاولة بعد قليل أو التواصل مع الدعم.",
    "Invalid payment mode.": "وضع الدفع غير صالح.",
    "Invalid PayRam mode.": "وضع PayRam غير صالح.",
    "Bad signature.": "توقيع الطلب غير صالح.",
    "Invalid payload.": "بيانات الطلب غير صالحة.",
    "Platform settings updated.": "تم تحديث إعدادات المنصة.",
    "Payment settings saved.": "تم حفظ إعدادات الدفع.",
    "Platform wallet saved.": "تم حفظ محفظة المنصة.",
    "Platform wallet removed.": "تم حذف محفظة المنصة.",
    "Platform wallet not found.": "محفظة المنصة غير موجودة.",
    "No known settings provided.": "لم يتم تقديم أي إعدادات معروفة.",
    "Nothing to update.": "لا يوجد ما يمكن تحديثه.",
    "Invalid numeric value for {key}.": "قيمة رقمية غير صالحة لحقل {key}.",
    "order_ref is required.": "حقل order_ref مطلوب.",
    "Payment gateway could not create the order.": "تعذّر على مزوّد الدفع إنشاء الطلب. يُرجى المحاولة مرة أخرى.",
    "Payment amount must be positive in USD.": "يجب أن يكون المبلغ أكبر من صفر بالدولار.",
    "Plisio is not configured (API key).": "خدمة الدفع غير مُهيأة حالياً. يُرجى المحاولة بعد قليل.",
    "Cryptomus is not configured (merchant id / payment key).": "خدمة الدفع غير مُهيأة حالياً. يُرجى المحاولة بعد قليل.",
    "Plisio created the invoice but returned no txn_id or invoice_url.": "تعذّر إنشاء طلب الدفع. يُرجى المحاولة مرة أخرى.",
    "Cryptomus created the payment but returned no address or checkout url.": "تعذّر إنشاء طلب الدفع. يُرجى المحاولة مرة أخرى.",
    "PayRam created the payment but returned no reference_id.": "تعذّر إنشاء طلب الدفع. يُرجى المحاولة مرة أخرى.",

    # KYC review (admin)
    "Submission not found.": "طلب التوثيق غير موجود.",
    "KYC approved for {email}.": "تمت الموافقة على توثيق {email}.",
    "KYC rejected for {email}.": "تم رفض توثيق {email}.",
    "Invalid file field.": "حقل الملف غير صالح.",
    "No file for this field.": "لا يوجد ملف مرفق لهذا الحقل.",
    "Could not open file.": "تعذّر فتح الملف.",

    # Admin users
    "User not found.": "المستخدم غير موجود.",
    "{email} frozen.": "تم تجميد حساب {email}.",
    "{email} unfrozen.": "تم إلغاء تجميد حساب {email}.",
    "{email} KYC approved.": "تمت الموافقة على توثيق {email}.",
    "{email} KYC rejected.": "تم رفض توثيق {email}.",
    "{email} banned until {until}.": "تم حظر {email} حتى {until}.",
    "{email} unbanned.": "تم إلغاء حظر {email}.",
    "Provide a positive number of hours.": "يرجى تقديم عدد ساعات أكبر من صفر.",
    "Type the user's email ({email}) to confirm deletion.": "اكتب بريد المستخدم ({email}) لتأكيد الحذف.",
    "You cannot delete your own account.": "لا يمكنك حذف حسابك الخاص.",
    "Account {email} permanently deleted.": "تم حذف حساب {email} نهائياً.",
    "Unknown action '{action}'.": "إجراء غير معروف '{action}'.",
    "target_user_ids must be a list of user ids.": "يجب أن تكون target_user_ids قائمة تحتوي على معرّفات المستخدمين.",
    "Invalid balance delta.": "قيمة تعديل الرصيد غير صالحة.",
    "No change requested.": "لم يتم طلب أي تعديل.",
    "Resulting balance cannot be negative.": "لا يمكن أن يكون الرصيد الناتج سالباً.",
    "Not found.": "غير موجود.",
}

# Gateway/config failures that interpolate runtime values (network lists, ids)
# and therefore cannot be listed in AR as exact keys. The captured group is
# re-inserted into the Arabic sentence; the English tail is dropped because it
# exposes internal provider details.
AR_DYNAMIC = [
    (
        re.compile(r"^(?P<net>[A-Za-z0-9_ ]+) is not supported by Plisio\."),
        "شبكة {net} غير مدعومة من مزوّد الدفع. يرجى اختيار شبكة أخرى.",
    ),
    (
        re.compile(r"^(?P<net>[A-Za-z0-9_ ]+) is not supported by the payment gateway\."),
        "شبكة {net} غير مدعومة من مزوّد الدفع. يرجى اختيار شبكة أخرى.",
    ),
]

# Django REST Framework / Django framework messages. Upstream ships no Arabic
# catalogue for these, so they are matched by shape instead of by exact key.
# Ordered: first match wins, so keep the specific patterns above the generic.
FRAMEWORK_AR = [
    (r"^This field is required\.$", "هذا الحقل مطلوب."),
    (r"^This field may not be null\.$", "لا يمكن ترك هذا الحقل فارغاً."),
    (r"^This field may not be blank\.$", "لا يمكن ترك هذا الحقل فارغاً."),
    (r"^A valid email address is required\.$", "مطلوب بريد إلكتروني صالح."),
    (r"^Enter a valid email address\.$", "أدخل بريداً إلكترونياً صالحاً."),
    (r"^Enter a valid URL\.$", "أدخل رابطاً صالحاً."),
    (r"^A valid URL is required\.$", "مطلوب رابط صالح."),
    (r"^Enter a valid number\.$", "أدخل رقماً صالحاً."),
    (r"^A valid number is required\.$", "مطلوب رقم صالح."),
    (r"^Enter a valid integer\.$", "أدخل عدداً صحيحاً."),
    (r"^A valid integer is required\.$", "مطلوب عدد صحيح صالح."),
    (r"^A valid boolean is required\.$", "مطلوب قيمة منطقية صالحة."),
    (r"^A valid date is required\.$", "مطلوب تاريخ صالح."),
    (r"^Enter a valid date\.$", "أدخل تاريخاً صالحاً."),
    (r"^This value is not a valid choice\.$", "هذه القيمة غير صالحة."),
    (r"^Ensure this field has no more than (\d+) characters\.$", "يجب ألا يزيد عدد أحرف هذا الحقل عن \\1."),
    (r"^Ensure this field has at least (\d+) characters\.$", "يجب ألا يقل عدد أحرف هذا الحقل عن \\1."),
    (r"^Ensure this field has at least (\d+) digits?\.$", "يجب أن يحتوي هذا الحقل على \\1 أرقام على الأقل."),
    (r"^Ensure this field has at least (\d+) decimal places?\.$", "يجب أن يحتوي هذا الحقل على \\1 منزلة عشرية على الأقل."),
    (r"^Ensure this field has at most (\d+) decimal places?\.$", "يجب ألا يحتوي هذا الحقل على أكثر من \\1 منزلة عشرية."),
    (r"^Ensure this field is greater than or equal to (.+)\.$", "يجب أن تكون هذه القيمة أكبر من أو تساوي \\1."),
    (r"^Ensure this field is less than or equal to (.+)\.$", "يجب أن تكون هذه القيمة أصغر من أو تساوي \\1."),
    (r"^Ensure this field is greater than (.+)\.$", "يجب أن تكون هذه القيمة أكبر من \\1."),
    (r"^Ensure this field is less than (.+)\.$", "يجب أن تكون هذه القيمة أصغر من \\1."),
    (r"^Ensure this value is greater than or equal to (.+)\.$", "يجب أن تكون هذه القيمة أكبر من أو تساوي \\1."),
    (r"^Ensure this value is less than or equal to (.+)\.$", "يجب أن تكون هذه القيمة أصغر من أو تساوي \\1."),
    (r"^Ensure this value is greater than (.+)\.$", "يجب أن تكون هذه القيمة أكبر من \\1."),
    (r"^Ensure this value is less than (.+)\.$", "يجب أن تكون هذه القيمة أصغر من \\1."),
    (r"^Invalid pk .*object does not exist\.$", "العنصر المطلوب غير موجود."),
    (r"^Invalid pk.*$", "العنصر المطلوب غير صالح."),
    (r"^Incorrect authentication credentials\.$", "بيانات الاعتماد غير صحيحة."),
    (r"^Authentication credentials were not provided\.$", "لم يتم تقديم بيانات الاعتماد."),
    (r"^No credentials provided\.$", "لم يتم تقديم بيانات الاعتماد."),
    (r"^Invalid token\.$", "الرمز غير صالح."),
    (r"^Token is invalid or expired\.$", "الرمز غير صالح أو منتهي الصلاحية."),
    (r"^Token has expired\.$", "انتهت صلاحية الرمز. يُرجى تسجيل الدخول مرة أخرى."),
    (r"^Token is blacklisted\.$", "الرمز غير صالح."),
    (r"^Given token not valid for any token type\.$", "الرمز غير صالح."),
    (r"^Error decoding token\.$", "تعذّر قراءة الرمز."),
    (r"^Token decoding failed\.$", "تعذّر قراءة الرمز."),
    (r"^You do not have permission to perform this action\.$", "ليست لديك صلاحية للقيام بهذا الإجراء."),
    (r"^The request is not valid\.$", "الطلب غير صالح."),
    (r"^The submitted data was not a form", "البيانات المرسلة غير صالحة."),
    (r"^No file was submitted\.$", "لم يتم إرسال أي ملف."),
    (r"^Could not parse parameters\.$", "تعذّر تحليل البيانات المُرسلة."),
    (r"^Request throttled\.$", "محاولات كثيرة. انتظر قليلاً ثم حاول مرة أخرى."),
    (r"^Method .* not allowed\.$", "طريقة الطلب غير مسموح بها."),
    (r"^Not found\.$", "غير موجود."),
    # Django password validators (belt-and-braces: Django's own catalog already
    # covers these once the language middleware activates).
    (r"^This password is too short\. It must contain at least (\d+) characters\.$", "كلمة المرور قصيرة جداً. يجب أن تحتوي على \\1 أحرف على الأقل."),
    (r"^This password is too long\. It must contain at most (\d+) characters\.$", "كلمة المرور طويلة جداً. يجب ألا تتجاوز \\1 حرفاً."),
    (r"^This password is too common\.$", "كلمة المرور شائعة جداً. اختر كلمة مرور أقوى."),
    (r"^This password is entirely numeric\.$", "كلمة المرور أرقام فقط. أضف حروفاً."),
    (r"^This password is too similar to the previous password\.$", "كلمة المرور مشابهة جداً لكلمة المرور السابقة."),
    (r"^The password is too similar to the user information\.$", "كلمة المرور مشابهة جداً لبياناتك."),
]

_FRAMEWORK_AR = [(re.compile(pattern), arabic) for pattern, arabic in FRAMEWORK_AR]


def translate_framework_message(text):
    """Return the Arabic rendering of a DRF/Django message, or None."""
    if not isinstance(text, str) or not text:
        return None
    for pattern, arabic in _FRAMEWORK_AR:
        if pattern.search(text):
            return pattern.sub(lambda _m: arabic, text, count=1)
    return None


def tr(text, request=None, **kwargs):
    """Translate a display string based on the request language."""
    lang = lang_of(request)
    if lang.startswith("ar"):
        translated = AR.get(str(text))
        if translated is None:
            # Gateway messages embed a runtime network list, so they can only be
            # matched by shape rather than by exact key.
            for pattern, arabic in AR_DYNAMIC:
                match = pattern.match(str(text))
                if match:
                    translated = arabic.format(**match.groupdict())
                    break
        if translated:
            text = translated
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text