import { ThreadCombLogo } from '../../components/brand/Logo';
import Link from 'next/link';

export const metadata = {
  title: 'Terms of Service - ThreadComb',
};

export default function TermsOfServicePage() {
  return (
    <div className="min-h-dvh bg-background">
      <header className="border-b border-border/40 bg-background/80 backdrop-blur-sm sticky top-0 z-30 px-6 md:px-10 py-5">
        <Link href="/">
          <ThreadCombLogo className="text-primary" />
        </Link>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-12 md:py-20 text-foreground">
        <h1 className="font-heading text-4xl font-medium mb-8">Terms of Service</h1>
        
        <div className="space-y-6 text-muted-foreground leading-relaxed">
          <p><strong>Last Updated:</strong> {new Date().toLocaleDateString()}</p>
          
          <section className="space-y-4">
            <h2 className="text-2xl font-medium text-foreground">1. Acceptance of Terms</h2>
            <p>
              By accessing or using ThreadComb, you agree to be bound by these Terms of Service. If you disagree 
              with any part of the terms, you may not access the service.
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-2xl font-medium text-foreground">2. Description of Service</h2>
            <p>
              ThreadComb is an AI-powered platform designed for creators to manage brand deals. We integrate with 
              your Gmail account via the Google Workspace API to read incoming emails, build an operational profile 
              ("Skills Audit"), and generate suggested drafts for deal negotiations and invoice follow-ups.
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-2xl font-medium text-foreground">3. Google API Integration</h2>
            <p>
              Our service requires access to your Google Account. Our use and transfer to any other app of information 
              received from Google APIs will adhere to the <a href="https://developers.google.com/terms/api-services-user-data-policy" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline mx-1">Google API Services User Data Policy</a>, including the 
              Limited Use requirements. We do not use your Google data for any purpose other than providing the core 
              features of ThreadComb.
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-2xl font-medium text-foreground">4. User Responsibilities</h2>
            <ul className="list-disc pl-5 space-y-2">
              <li>You are responsible for maintaining the confidentiality of your account credentials.</li>
              <li>You agree to review and approve all AI-generated email drafts before sending them. ThreadComb is an assistant, and you remain solely responsible for any communications sent from your account.</li>
              <li>You must not use the service for any illegal or unauthorized purpose.</li>
            </ul>
          </section>

          <section className="space-y-4">
            <h2 className="text-2xl font-medium text-foreground">5. Intellectual Property</h2>
            <p>
              The service and its original content, features, and functionality are and will remain the exclusive 
              property of ThreadComb and its licensors. 
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-2xl font-medium text-foreground">6. Limitation of Liability</h2>
            <p>
              In no event shall ThreadComb, nor its directors, employees, partners, agents, suppliers, or affiliates, 
              be liable for any indirect, incidental, special, consequential or punitive damages, including without 
              limitation, loss of profits, data, use, goodwill, or other intangible losses, resulting from your access 
              to or use of or inability to access or use the Service.
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-2xl font-medium text-foreground">7. Changes to Terms</h2>
            <p>
              We reserve the right, at our sole discretion, to modify or replace these Terms at any time. We will 
              provide notice of any material changes via email or prominently on our platform.
            </p>
          </section>

          <section className="space-y-4">
            <h2 className="text-2xl font-medium text-foreground">8. Contact Us</h2>
            <p>
              If you have any questions about these Terms, please contact us at <a href="mailto:contact@threadcomb.com" className="text-primary hover:underline">contact@threadcomb.com</a>.
            </p>
          </section>
        </div>
      </main>
    </div>
  );
}
