import { ThreadCombLogo } from '../../components/brand/Logo';
import Link from 'next/link';

export const metadata = {
  title: 'Privacy Policy - ThreadComb',
};

export default function PrivacyPolicyPage() {
  return (
    <div className="min-h-dvh bg-background">
      <header className="border-b border-border/40 bg-background/80 backdrop-blur-sm sticky top-0 z-30 px-6 md:px-10 py-5">
        <Link href="/">
          <ThreadCombLogo className="text-primary" />
        </Link>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-12 md:py-20 text-foreground">
        <h1 className="font-heading text-4xl font-medium mb-8">Privacy Policy</h1>
        
        <div className="space-y-6 text-muted-foreground leading-relaxed">
          <p><strong>Last Updated:</strong> {new Date().toLocaleDateString()}</p>
          
          <section className="space-y-4">
            <h2 className="text-2xl font-medium text-foreground">1. Introduction</h2>
            <p>
              Welcome to ThreadComb. We respect your privacy and are committed to protecting your personal data. 
              This privacy policy explains how we collect, use, and safeguard your information when you use our 
              services, particularly concerning our integration with Google Workspace and Gmail APIs.
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-2xl font-medium text-foreground">2. Google Workspace API Data Usage</h2>
            <p>
              ThreadComb's use and transfer of information received from Google APIs to any other app will adhere to 
              <a href="https://developers.google.com/terms/api-services-user-data-policy" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline mx-1">
                Google API Services User Data Policy
              </a>, including the Limited Use requirements.
            </p>
            <ul className="list-disc pl-5 space-y-2">
              <li><strong>What we read:</strong> We only access email threads relevant to brand deals, negotiations, and invoices to provide you with insights and auto-drafted replies.</li>
              <li><strong>What we store:</strong> We extract and store structured metadata (like deal amounts, dates, and brand names). We <strong>do not</strong> store the raw body text of your emails permanently.</li>
              <li><strong>Who has access:</strong> Only you have access to your parsed data. We do not sell your data to third parties. Our AI models act strictly as data processors.</li>
            </ul>
          </section>

          <section className="space-y-4">
            <h2 className="text-2xl font-medium text-foreground">3. Information We Collect</h2>
            <p>
              When you use ThreadComb, we collect:
            </p>
            <ul className="list-disc pl-5 space-y-2">
              <li><strong>Account Information:</strong> Name, email address, and profile picture provided via Google OAuth.</li>
              <li><strong>Operational Data:</strong> Data parsed from your brand deal communications to generate your Skills Audit and draft replies.</li>
              <li><strong>Usage Data:</strong> Basic analytics to understand how our application is used to improve our services.</li>
            </ul>
          </section>

          <section className="space-y-4">
            <h2 className="text-2xl font-medium text-foreground">4. How We Use Your Information</h2>
            <p>We use your information exclusively to:</p>
            <ul className="list-disc pl-5 space-y-2">
              <li>Provide, operate, and maintain our service.</li>
              <li>Analyze your negotiation patterns to generate your personalized Skills Audit.</li>
              <li>Draft context-aware email replies for your brand deals.</li>
              <li>Track overdue invoices and suggest follow-ups.</li>
            </ul>
          </section>

          <section className="space-y-4">
            <h2 className="text-2xl font-medium text-foreground">5. Data Security</h2>
            <p>
              We implement industry-standard security measures to protect your data. All communication is encrypted 
              in transit (HTTPS/TLS) and data is encrypted at rest. We utilize secure OAuth tokens rather than 
              storing passwords.
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-2xl font-medium text-foreground">6. Your Rights</h2>
            <p>
              You have the right to access, update, or delete your personal data at any time. You can revoke 
              ThreadComb's access to your Google Account directly from your Google Security settings. Upon account 
              deletion, all your parsed data and metadata will be permanently erased from our systems.
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-2xl font-medium text-foreground">7. Contact Us</h2>
            <p>
              If you have any questions about this Privacy Policy, please contact us at <a href="mailto:contact@threadcomb.com" className="text-primary hover:underline">contact@threadcomb.com</a>.
            </p>
          </section>
        </div>
      </main>
    </div>
  );
}
