import { LegalShell } from '../components/LegalShell'

export default function Privacy() {
  return (
    <LegalShell title="Privacy Policy" updated="September 11, 2026">
      <h2>1. Overview</h2>
      <p>
        This Privacy Policy explains how Zevra collects, uses, stores, and shares your personal data when
        you use the Platform. We process your data to operate the service, comply with legal obligations,
        and keep the Platform safe.
      </p>

      <h2>2. Data we collect</h2>
      <ul>
        <li><b>Account data:</b> name, email, phone number, avatar, and login activity.</li>
        <li><b>Verification data:</b> KYC documents (ID images, selfies) provided for identity checks.</li>
        <li><b>Financial data:</b> investment amounts, balances, crypto addresses, withdrawal and payout records.</li>
        <li><b>Technical data:</b> IP address, device and browser information, and usage logs collected automatically.</li>
      </ul>

      <h2>3. How we use data</h2>
      <p>We use your data to:</p>
      <ul>
        <li>Create and manage your account and balances;</li>
        <li>Process investments, withdrawals, and payouts;</li>
        <li>Prevent fraud, money laundering, and abuse;</li>
        <li>Meet anti-money-laundering (AML) and KYC legal duties;</li>
        <li>Provide support and communicate service updates;</li>
        <li>Improve and secure the Platform.</li>
      </ul>

      <h2>4. Legal basis</h2>
      <p>
        We process data based on your consent, the performance of our contract with you, our legitimate
        interest in a secure service, and legal obligations applicable to financial and virtual-asset
        businesses.
      </p>

      <h2>5. Sharing</h2>
      <p>
        We do not sell your personal data. We may share data with: service providers who help operate the
        Platform (subject to confidentiality), regulators and law enforcement where required by law, and
        professional advisors such as auditors and legal counsel.
      </p>

      <h2>6. KYC documents</h2>
      <p>
        Verification documents are stored securely, access is restricted to trained compliance staff, and
        they are retained only as long as required by law. You may request deletion after the legal
        retention period ends.
      </p>

      <h2>7. Security</h2>
      <p>
        We use industry-standard technical and organizational measures, including encryption in transit,
        hashed/salted passwords, access controls, and continuous monitoring. No method of transmission
        over the internet is 100% secure.
      </p>

      <h2>8. Cookies and storage</h2>
      <p>
        We use authentication tokens (stored on your device) to keep you signed in. We do not use
        third-party advertising cookies on the Platform.
      </p>

      <h2>9. Your rights</h2>
      <p>
        Depending on your jurisdiction, you may have the right to access, correct, delete, or export your
        data, and to object to or restrict certain processing. To exercise these rights, contact support.
      </p>

      <h2>10. Data retention</h2>
      <p>
        We retain financial and compliance records for as long as required by law (generally at least five
        years for AML purposes), and other data while your account is active.
      </p>

      <h2>11. International transfers</h2>
      <p>
        Your data may be processed in countries other than your own. When we transfer data across borders,
        we apply appropriate safeguards required by applicable law.
      </p>

      <h2>12. Children</h2>
      <p>The Platform is not directed at anyone under 18. We do not knowingly collect data from minors.</p>

      <h2>13. Changes</h2>
      <p>
        We may update this policy. Material changes will be notified on the Platform and the effective date
        will be updated at the top of this page.
      </p>

      <h2>14. Contact</h2>
      <p>For privacy questions or to exercise your rights, contact support through the Platform.</p>
    </LegalShell>
  )
}