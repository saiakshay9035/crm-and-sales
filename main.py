import time
import logging
from scraper import StartupLeadScraper
from enricher import AIProspectEnricher
from crm_client import CompAICRMClient
from outreach import EmailOutreachManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("AutonomousLeadAgent")

def run_lead_generation_pipeline(dry_run: bool = False, delay_seconds: int = 2):
    print("=" * 70)
    print("      AUTONOMOUS AI LEAD & OUTREACH AGENT FOR MANAGED TECH TALENT     ")
    print("      Integrated with trycompai/crm (Comp AI Agentic CRM)             ")
    print("=" * 70)
    
    # 1. Initialize System Components
    scraper = StartupLeadScraper()
    enricher = AIProspectEnricher()
    crm = CompAICRMClient()
    outreach = EmailOutreachManager(dry_run=dry_run)

    # 2. Step 1: Scrape target startups
    logger.info("Step 1: Finding target startups in US, UAE, Australia, and EU...")
    try:
        startups = scraper.scrape_yc_startups(sample_limit=4)
    except Exception as e:
        logger.error(f"Failed to scrape startups: {e}")
        return

    print(f"-> Found {len(startups)} target startup leads.\n")

    success_count = 0
    failure_count = 0

    # 3. Step 2 & 3: Process, Enrich, Log to Comp AI CRM, and Dispatch
    for idx, lead in enumerate(startups, 1):
        print(f"[{idx}/{len(startups)}] Processing {lead['company_name']} ({lead['location']})...")
        
        try:
            # A. Log Company in Comp AI CRM
            company_record = crm.create_or_update_company(
                name=lead['company_name'],
                domain=lead['domain'],
                location=lead['location'],
                summary=lead['tech_summary']
            )
            
            # B. Generate AI Personalized Outreach Pitch
            pitch = enricher.generate_pitch(
                founder_name=lead['founder_name'],
                company_name=lead['company_name'],
                location=lead['location'],
                summary=lead['tech_summary']
            )
            
            print("\n--- AI Generated Personalized Pitch ---")
            print(pitch)
            print("---------------------------------------\n")
            
            # C. Create Lead Contact in Comp AI CRM
            contact_record = crm.create_or_update_contact(
                company_id=company_record.get("id", "temp_id"),
                name=lead['founder_name'],
                email=lead['email'],
                title=lead['founder_title'],
                pitch_draft=pitch
            )
            
            # D. Send Cold Email
            sent_success = outreach.send_email(
                to_email=lead['email'],
                pitch_content=pitch
            )
            
            # E. Log Interaction in Comp AI CRM
            if sent_success:
                crm.log_interaction(
                    contact_id=contact_record.get("id", "temp_contact_id"),
                    action_type="EMAIL_SENT",
                    content=f"Sent initial outreach pitch to {lead['email']}"
                )
                success_count += 1
            else:
                logger.error(f"Failed to send email to {lead['email']}.")
                failure_count += 1
                
        except Exception as e:
            logger.error(f"Error processing lead {lead.get('company_name', 'Unknown')}: {e}")
            failure_count += 1
            
        time.sleep(delay_seconds)

    print("\n" + "=" * 70)
    print("PIPELINE SUMMARY:")
    print(f"Successful Leads Processed: {success_count}")
    print(f"Failed Leads: {failure_count}")
    if dry_run:
        print("NOTE: Executed in DRY RUN mode. Set dry_run=False in main.py to send real emails.")
    else:
        print("LIVE MODE ACTIVE: Emails dispatched.")
    print("=" * 70)

if __name__ == "__main__":
    # Live mode active
    run_lead_generation_pipeline(dry_run=False, delay_seconds=2)
