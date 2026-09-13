import { LegalShell } from '../components/LegalShell'

export default function KycPolicy() {
  return (
    <LegalShell title="AML & KYC Policy" updated="September 11, 2026">
      <h2>1. Purpose</h2>
      <p>
        Zevra is committed to preventing money laundering, terrorist financing, fraud, and other financial
        crime. This policy sets out the identity verification (KYC) and anti-money-laundering (AML)
        measures applied to all users.
      </p>

      <h2>2. When verification is required</h2>
      <p>
        The administration may require KYC verification before a user can invest, withdraw, or receive
        payouts. Requirements are controlled by the administration and can be enabled or disabled.
        Users may also be asked to verify at any point based on risk assessment or transaction thresholds.
      </p>

      <h2>3. What we verify</h2>
      <ul>
        <li>Full legal name and contact details;</li>
        <li>A government-issued photo ID (ID card, passport, or driver's license);</li>
        <li>A selfie or liveliness check confirming the ID belongs to the user;</li>
        <li>Source-of-funds information where required by law.</li>
      </ul>

      <h2>4. Review process</h2>
      <p>
        Submissions are reviewed by trained staff. Typical reviews are completed within a few business days.
        If documents cannot be verified, the submission is rejected with a reason and the user may resubmit.
        Submissions may be re-reviewed at any time.
      </p>

      <h2>5. Sanctions screening</h2>
      <p>
        Account data is screened against applicable sanctions lists and government watchlists. Accounts
        matching restricted persons or entities may be frozen and reported to the relevant authorities.
      </p>

      <h2>6. Transaction monitoring</h2>
      <p>
        We monitor activity for unusual patterns (e.g., rapid deposits and withdrawals, round-tripping,
        layering, transactions involving high-risk jurisdictions). Suspicious activity may result in account
        review, freezing, or reporting to financial intelligence units as required by law.
      </p>

      <h2>7. Record keeping</h2>
      <p>
        Records of identity verification and transactions are retained for at least the period required by
        applicable law (typically five years or more).
      </p>

      <h2>8. Refusals</h2>
      <p>
        We may refuse or terminate service, withhold payouts, or freeze balances where required by law,
        where verification fails, or where activity is suspected to be unlawful. Cooperation with lawful
        authorities takes priority over user requests.
      </p>

      <h2>9. Changes</h2>
      <p>
        This policy may be updated to reflect legal or operational changes. Continued use of the Platform
        constitutes acceptance of the current policy.
      </p>
    </LegalShell>
  )
}