# Publish Zevra — App Store & Google Play

Zevra is a **PWA** (progressive web app). It is installable from the browser on
iOS and Android today. For a store presence you have two options:

| Option | Effort | Notes |
|--------|--------|-------|
| A. Ship the PWA + store listing | Low | iOS App Store links "Add to Home Screen" from Safari; Google Play carries PWAs via Trusted Web Activity. Fastest path. |
| B. Native wrappers (Capacitor/TWA) | Medium | Wrap the same web app in a Capacitor shell (iOS/Android). You need Xcode + Android Studio and Apple/Google developer accounts. |

Either way you must publish real legal documents and answer store compliance
questions. The compiled documents live in this folder and are served on the
website under `/terms`, `/privacy`, and `/kyc-policy`.

---

## Things stores require (both stores)

1. **Privacy Policy URL** — publish `PRIVACY_POLICY.md` (served at `/privacy`)
   on a public HTTPS URL. Both stores will run a compliance scan on it.
2. **Terms of Service URL** — publish `TERMS_OF_SERVICE.md` (served at `/terms`).
3. **Working account recovery and a real point of contact** — "email/password"
   must be recoverable and you need a support address.
4. **No placeholder or empty app** — the app must open to a real screen.
5. **Data reporting** — declare what you collect (email, name, phone, photos,
   financial/transaction data, user content) and how it is used.

> A financial multi-level-referral app is high-risk for review. Both stores will
> scrutinize: is it gambling / a pyramid scheme / an unlicensed securities or
> money-services business? You **must** obtain qualified legal advice and, in
> most jurisdictions, a license or registration before offering it publicly.
> These documents do not guarantee approval or legality.

---

## Apple App Store (option B / Capacitor)

- **Account**: Apple Developer Program ($99/yr) at developer.apple.com.
- **Category**: Finance (or Business). Check boxes you trigger: user content,
  contacts, identifiers, usage data.
- **Required screenshots**: 6.9" (iPhone 14 Pro Max), 6.5", 5.5" and iPad sizes.
- **App icon**: 1024×1024, no transparency.
- **Privacy "nutrition label"**: Data not linked: Crash data, Diagnostics,
  Usage data. Data linked: Name, Email, Phone number, Photos, IDs, Financial info,
  User content, Purchase history.
- **IDFA**: not used (no ad tracking).
- **Account deletion**: provided in-app under Profile → Delete account. Because
  retained data maps to the account, explain retention in the policy (AML).
- **App Reviewer guidance**: include a demo account or a note explaining
  KYC-gated flows so reviewers can get in.

### App Store metadata

```text
Name        : Zevra — Invest & Trade
Subtitle    : Stablecoin investing & referrals
Keywords    : invest, crypto, stablecoin, trading, referral, blockchain
Category    : Finance
Age rating  : 17+ (unrestricted web access + financial content)
``` <!-- keep data-safety consistent with Google Play answers -->

## Google Play Store (option A: PWA in Trusted Web Activity, or option B)

- **Account**: Google Play Console ($25 one-time).
- **App type**: App; **category**: Finance; confirm the financial-services
  declaration. Play will ask about virtual currency and crypto.
- **Data safety form** — answer consistently:

```text
Collected data:
  Personal info — name, email, phone           Purpose: account mgmt, fraud
  Photos — avatar, KYC documents               Purpose: account mgmt, verification
  Financial info — transactions, balances      Purpose: app functionality, fraud
  App activity / performance                   Collected: anonymized
Encrypted in transit:          YES
Data deleted on account close: partial (KYC/transactions retained per AML law —
                                  stated in the privacy policy)
Data shared:                  no sale; shared only with providers/authorities
```

- **Content rating**: complete the questionnaire (financial content → rate it
  for your target age).
- **Publish a demo / test instructions** for the reviewer (e.g., a sandbox
  account), since KYC gates will otherwise block the review flow.

---

## Before you submit — checklist

- [ ] Legal review by a lawyer (Terms, Privacy, AML/KYC, payout rules)
- [ ] Real support email + published contact
- [ ] `EMAIL_BACKEND` configured (password reset must actually send mail)
- [ ] HTTPS deployment; `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` set
- [ ] `payment_mode` set to a real provider and tested with tiny amounts
- [ ] Screenshots of Dashboard, Market, Invest, Withdraw, Referrals, Profile
- [ ] KYC gate: decide and set `kyc_required_to_invest` / `_to_withdraw`
- [ ] Age/managed markets consent confirmed on both consoles