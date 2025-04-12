import os
import re
import random
import asyncio
from datetime import datetime, timedelta
from google import genai
from google.genai import types
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
import asyncpg

load_dotenv()

app = Flask(__name__)

# Set up Gemini API key from .env file
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
)

# Neon DB connection parameters
NEON_DB_USER = os.getenv("NEON_DB_USER")
NEON_DB_PASSWORD = os.getenv("NEON_DB_PASSWORD")
NEON_DB_HOST = os.getenv("NEON_DB_HOST")
NEON_DB_PORT = os.getenv("NEON_DB_PORT")
NEON_DB_NAME = os.getenv("NEON_DB_NAME")

# Function to connect to Neon DB
async def connect_to_neon():
    try:
        return await asyncpg.connect(
            user=NEON_DB_USER,
            password=NEON_DB_PASSWORD,
            database=NEON_DB_NAME,
            host=NEON_DB_HOST,
            port=NEON_DB_PORT
        )
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

# Function to get conversation summary for a phone number
async def get_conversation_summary(phone_number):
    """Fetch conversation summary for a given phone number"""
    try:
        conn = await connect_to_neon()
        if not conn:
            return None
        
        # Check if we have logs for this phone number
        row = await conn.fetchrow("SELECT summary FROM logs WHERE phone = $1", phone_number)
        
        if row:
            return row['summary']
        return None
    except Exception as e:
        print(f"Error fetching conversation summary: {e}")
        return None
    finally:
        if conn:
            await conn.close()

# Function to update conversation summary
async def update_conversation_summary(phone_number, user_message, ai_response):
    """Update or create conversation summary for a given phone number"""
    try:
        conn = await connect_to_neon()
        if not conn:
            return False
        
        # Check if we have a record for this phone number
        row = await conn.fetchrow("SELECT summary FROM logs WHERE phone = $1", phone_number)
        
        # Create log entry for this conversation
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_log_entry = f"[{timestamp}] User: {user_message} | Assistant: {ai_response}"
        
        if row:
            # Get existing log and summary
            existing_summary = row['summary']
            
            # Generate new summary with Gemini
            prompt = (
                f"Based on this previous conversation summary: '{existing_summary}' "
                f"and this new exchange - User: '{user_message}' and Assistant: '{ai_response}', "
                f"provide a concise updated summary of the conversation so far. "
                f"Keep important details about the user's needs and context. "
                f"Format as 'Summary of conversation so far: [your summary]. Last message from user: {user_message}'"
            )
            
            summary_response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[prompt]
            ).text.strip()
            
            # Update the existing record
            await conn.execute(
                "UPDATE logs SET summary = $1 WHERE phone = $2",
                summary_response, phone_number
            )
        else:
            # Create initial summary
            summary = f"Summary of conversation so far: Initial contact from user. Last message from user: {user_message}"
            
            # Create a new record
            await conn.execute(
                "INSERT INTO logs (phone, summary) VALUES ($1, $2)",
                phone_number, summary
            )
            
            summary_response = summary
        
        return summary_response
    except Exception as e:
        print(f"Error updating conversation summary: {e}")
        return None
    finally:
        if conn:
            await conn.close()

# Dummy donation data (in-memory dictionary for reference)
DUMMY_DONATIONS = {
    "+919876543210": [
        {"amount": 3000, "date": "2025-03-02", "utr": "UTR789456", "receipt_sent": False, "donor_name": "Rajesh Sharma", "payment_method": "UPI", "campaign": "Education Fund"},
        {"amount": 5000, "date": "2024-12-15", "utr": "UTR123789", "receipt_sent": True, "donor_name": "Rajesh Sharma", "payment_method": "Bank Transfer", "campaign": "Winter Relief"}
    ],
    "+918765432109": [
        {"amount": 10000, "date": "2025-04-01", "utr": "UTR456123", "receipt_sent": True, "donor_name": "Priya Patel", "payment_method": "Credit Card", "campaign": "Healthcare Initiative"},
        {"amount": 2500, "date": "2025-01-10", "utr": "UTR987234", "receipt_sent": True, "donor_name": "Priya Patel", "payment_method": "UPI", "campaign": "Education Fund"}
    ],
    "+917654321098": [
        {"amount": 50000, "date": "2025-03-15", "utr": "UTR567890", "receipt_sent": False, "donor_name": "Amit Verma", "payment_method": "Bank Transfer", "campaign": "Rural Development"},
        {"amount": 15000, "date": "2024-11-05", "utr": "UTR345678", "receipt_sent": True, "donor_name": "Amit Verma", "payment_method": "UPI", "campaign": "Clean Water Project"}
    ],
    "+916543210987": [
        {"amount": 1000, "date": "2025-03-28", "utr": "UTR654321", "receipt_sent": True, "donor_name": "Sneha Gupta", "payment_method": "UPI", "campaign": "Education Fund"}
    ],
    "+915432109876": [],  # New donor with no history
    "+919780086800": [
        {"amount": 2000, "date": "2025-02-18", "utr": "UTR123456", "receipt_sent": True, "donor_name": "Arvin Kumar", "payment_method": "UPI", "campaign": "Education Fund"}
    ]
}

# Email addresses for dummy data (using phone number as key for simplicity in this context)
DONOR_EMAILS = {
    "+919876543210": "rajesh.sharma@example.com",
    "+918765432109": "priya.patel@example.com",
    "+917654321098": "amit.verma@example.com",
    "+916543210987": "sneha.gupta@example.com",
    "+915432109876": "new.donor@example.com",
    "+919780086800": "arvin.kumar@example.com"
}

# Enhanced context for the assistant
LONG_CONTEXT = """
Narayan Shiva Sansthan:

ABOUT US:
- Narayan Shiva Sansthan is a registered charitable organization (Reg. No. CHT/2008/45678)
- Founded in 2008 with a mission to create sustainable impact across underserved communities
- 95% of donations go directly to our programs and beneficiaries
- Transparent financial reporting available on our website quarterly

DONATION OPTIONS:
- UPI: donations@NarayanShivaSansthan
- Credit/Debit Cards: Processed securely through our payment gateway
- Bank Transfer: Account No: 12345678901, IFSC: HDHF0001234, Narayan Shiva Sansthan
- Cheque: Payable to "Narayan Shiva Sansthan" and mailed to our office
- Monthly recurring donations available with a minimum of ₹100/month

TAX BENEFITS:
- All donations are eligible for tax benefits under Section 80G
- Tax receipts are automatically generated for donations above ₹500
- For donations above ₹50,000, additional KYC documentation is required (PAN card copy)
- Foreign donations are processed under FCRA regulations

PROJECTS AND CAMPAIGNS:
1. Education Fund: Supports scholarships and school infrastructure in rural areas
2. Healthcare Initiative: Mobile medical camps and primary healthcare centers
3. Rural Development: Skill training, microfinance, and sustainable farming practices
4. Clean Water Project: Installing water purification systems in villages
5. Winter Relief: Blankets and warm clothing distribution in northern regions
6. Disaster Response: Emergency relief during natural calamities

DONOR SERVICES:
- Receipts are typically sent within 24-48 hours of donation confirmation
- Donors can track their donations using UTR numbers through our online portal
- Regular impact reports are sent to all donors quarterly
- Donor helpdesk available Monday-Saturday (10am-6pm) at +91 88888-55555
- For urgent receipt issues, contact receipts@narayanss.org

VOLUNTEERING:
- Volunteer opportunities available across all our projects
- Corporate volunteering programs for team-building activities
- Weekend volunteering drives in local communities
- Register as a volunteer at volunteer@narayanss.org

OFFICE ADDRESS:
Narayan Shiva Sansthan
123 Charity Lane, Saket
New Delhi - 110017
"""

OFFICE_HOURS = "Monday to Saturday, 10:00 AM to 6:00 PM"
CURRENT_CAMPAIGNS = ["Education Fund", "Healthcare Initiative", "Clean Water Project", "Summer Relief 2025"]

def identify_intent(query):
    query_lower = query.lower()

    # More detailed intent identification
    if any(word in query_lower for word in ["donate", "contribution", "give", "support", "contribute", "payment"]):
        return "donation_intent"
    elif any(word in query_lower for word in ["receipt", "tax", "acknowledgment", "certificate", "80g"]) and any(word in query_lower for word in ["didn't get", "haven't received", "missing", "where", "not received"]):
        return "receipt_issue"
    elif any(word in query_lower for word in ["utr", "transaction", "payment", "confirm", "successful", "went through"]):
        return "utr_verification"
    elif any(word in query_lower for word in ["volunteer", "volunteering", "help out", "join", "participate"]):
        return "volunteer_inquiry"
    elif any(word in query_lower for word in ["tax benefit", "80g", "deduction", "tax exemption"]):
        return "tax_benefit_inquiry"
    elif any(word in query_lower for word in ["project", "campaign", "initiative", "program", "what do you do"]):
        return "project_inquiry"
    elif any(word in query_lower for word in ["office", "location", "address", "visit", "come to"]):
        return "office_inquiry"
    else:
        return "general_inquiry"

def extract_info_from_query(query):
    # Extract UTR if mentioned
    utr_match = re.search(r'UTR\d+', query, re.IGNORECASE)
    utr = utr_match.group(0) if utr_match else None

    # Extract amount if mentioned
    amount_match = re.search(r'₹\s*(\d+)', query) or re.search(r'Rs\.?\s*(\d+)', query) or re.search(r'(\d+)\s*rupees', query, re.IGNORECASE)
    amount = amount_match.group(1) if amount_match else None

    # Extract phone number if mentioned
    phone_match = re.search(r'(\+91\s?)?[789]\d{9}', query) or re.search(r'(\+91\s?)?[789]\d\d\d\d\s?\d\d\d\d\d', query)
    phone = phone_match.group(0) if phone_match else None

    # Extract name if mentioned (simple version)
    name_indicators = ["name is", "this is", "called", "speaking", "named", "by the name"]
    name = None
    for indicator in name_indicators:
        if indicator in query.lower():
            parts = query.lower().split(indicator)
            if len(parts) > 1:
                potential_name = parts[1].strip().split()[0].capitalize()
                if len(potential_name) > 2:  # Avoid picking up small words
                    name = potential_name
                    break

    # Check for specific names in the text
    common_names = ["Arvin", "Rajesh", "Priya", "Amit", "Sneha"]
    for common_name in common_names:
        if common_name.lower() in query.lower():
            name = common_name
            break

    return {"utr": utr, "amount": amount, "phone": phone, "name": name}

def get_user_id_from_info(extracted_info, sender_phone):
    # First, check if the sender's phone number exists in our records
    if sender_phone in DUMMY_DONATIONS:
        return sender_phone

    # If not, try to match by UTR
    if extracted_info["utr"]:
        for phone, donations in DUMMY_DONATIONS.items():
            if any(d.get("utr", "") == extracted_info["utr"] for d in donations):
                return phone

    # If no UTR match, try to match by name
    if extracted_info["name"]:
        for phone, donations in DUMMY_DONATIONS.items():
            if donations and any(extracted_info["name"].lower() in d.get("donor_name", "").lower() for d in donations):
                return phone

    # If a phone number is explicitly mentioned in the query, try to use that
    if extracted_info["phone"] and extracted_info["phone"] in DUMMY_DONATIONS:
        return extracted_info["phone"]
    elif extracted_info["phone"]:
        # Clean the extracted phone number for potential matching
        cleaned_phone = "".join(filter(str.isdigit, extracted_info["phone"]))
        for phone in DUMMY_DONATIONS:
            cleaned_donor_phone = "".join(filter(str.isdigit, phone))
            if cleaned_phone[-10:] == cleaned_donor_phone[-10:]:
                return phone

    # Special case for Arvin (can be identified by name or a specific part of his number)
    if extracted_info["name"] == "Arvin":
        return "+919780086800"
    elif extracted_info["phone"] and "97800" in extracted_info["phone"]:
        return "+919780086800"

    # Default to sender's phone
    return sender_phone

async def generate_response_async(query, sender_phone):
    model = "gemini-2.0-flash"

    # Extract information and identify intent
    extracted_info = extract_info_from_query(query)
    intent = identify_intent(query)

    # Determine user ID (using phone number as ID in this context)
    user_phone = get_user_id_from_info(extracted_info, sender_phone)

    # Get conversation summary from Neon DB
    conversation_summary = await get_conversation_summary(user_phone)
    
    # Build user context with detailed information
    user_context = ""
    if user_phone and user_phone in DUMMY_DONATIONS and DUMMY_DONATIONS[user_phone]:
        user_context = f"\nDonor Information:\nName: {DUMMY_DONATIONS[user_phone][0].get('donor_name')}\nPhone: {user_phone}\nEmail: {DONOR_EMAILS.get(user_phone)}\n\nDonation History:\n"
        for d in DUMMY_DONATIONS[user_phone]:
            receipt_status = "Sent on " + (datetime.strptime(d.get('date'), "%Y-%m-%d") + timedelta(days=2)).strftime("%Y-%m-%d") if d.get("receipt_sent") else "Pending - Will be sent within 24 hours"
            user_context += f"- ₹{d.get('amount')} on {d.get('date')} for {d.get('campaign')}, via {d.get('payment_method')}, UTR: {d.get('utr')}, Receipt Status: {receipt_status}\n"
    else:
        user_context = "\nThis appears to be a new donor with no previous donation history in our system.\n"

    # Include conversation history if available
    conversation_context = ""
    if conversation_summary:
        conversation_context = f"\nConversation Summary:\n{conversation_summary}\n"

    # Add current date and time context
    current_datetime = datetime.now().strftime("%Y-%m-%d, %A, %H:%M")
    time_context = f"\nCurrent Date and Time: {current_datetime}\nOffice Hours: {OFFICE_HOURS}\nActive Campaigns: {', '.join(CURRENT_CAMPAIGNS)}\n"

    system_instruction = f"""You are Ananya, a friendly and helpful receptionist at Narayan Shiva Sansthan, a charitable organization.
Your role is to assist donors, potential donors, and anyone with inquiries about the foundation via WhatsApp.
Always be warm, personable, and speak as if you're responding from our charity office.

Use Indian expressions and references where appropriate. Address people respectfully, using "ji" occasionally.
If the conversation seems to be in Hindi or any regional language, respond accordingly.

Current information:
{time_context}

Donor information:
{user_context}

Previous conversation context:
{conversation_context}

Foundation information:
{LONG_CONTEXT}

When starting a conversation:
- Use phrases like "Namaste!", "Hello!", or "Welcome to Narayan Shiva Sansthan!"
- Introduce yourself as Ananya from the reception desk.
- Thank donors for their support and generosity if they mention past donations.

IMPORTANT: Never include any "acting" or roleplay elements in your responses. Do not include phrases like "(slight pause)" or descriptions of your actions. Simply respond as if you're having a natural conversation. Keep your responses concise for WhatsApp.

Guidelines based on inquiry type:
1. For donation intents - Express gratitude, provide donation options, and the donation link (https://donate.narayanss.org)
2. For receipt issues - Check the donation history, apologize for any delays, and offer to expedite. If a UTR is provided, try to locate the donation.
3. For UTR verifications - Confirm transactions from the donation history if available.
4. For volunteer inquiries - Share volunteer opportunities and ask for their areas of interest. Provide contact info if needed (volunteer@narayanss.org).
5. For tax benefit inquiries - Explain Section 80G benefits clearly and what documentation we provide.
6. For office inquiries - Share our address and invite them to visit during office hours.
7. For project inquiries - Describe our current initiatives with enthusiasm and share brief success stories.

Important notes:
- Be compassionate and patient, especially with donation-related concerns.
- If you don't have certain information, offer to connect them with the appropriate team member or provide a contact number (+91 88888-55555).
- Always express gratitude for their interest in our foundation.
- End conversations warmly and ask if there's anything else you can assist with.
- Your responses should be concise and professional for WhatsApp.

Remember, you're the friendly voice of Narayan Shiva Sansthan Foundation on WhatsApp!
"""

    generate_config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.7,  # Slightly higher temperature for more personable responses
        max_output_tokens=1000, # Adjusted for concise WhatsApp responses
    )

    contents = [query]
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=generate_config
    )

    response_text = response.text if response.text else "Sorry, I couldn't generate a response at the moment."
    
    # Update conversation summary in the database
    await update_conversation_summary(user_phone, query, response_text)
    
    return response_text

# Create a synchronous wrapper for the async function
def generate_response(query, sender_phone):
    return asyncio.run(generate_response_async(query, sender_phone))

@app.route('/twilio_webhook', methods=['POST'])
def twilio_webhook():
    print("Raw Twilio Request Data:")
    print(request.form)

    sender_phone = request.form.get('From')
    message_body = request.form.get('Body')

    print(f"Phone number from request: {sender_phone}")
    print(f"Message body from request: {message_body}")

    if not sender_phone or not message_body:
        error_message = "<Response><Message>Error: Phone number and message are required.</Message></Response>"
        return error_message, 400, {'Content-Type': 'application/xml'}

    # Extract phone number from Twilio format
    if sender_phone.startswith('whatsapp:'):
        sender_phone = sender_phone.replace('whatsapp:', '')

    response_text = generate_response(message_body, sender_phone)

    response = MessagingResponse()
    response.message(response_text)

    twiml_string = str(response)

    return twiml_string, 200, {'Content-Type': 'application/xml'}

@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint to check the health of the application."""
    return jsonify({"status": "ok", "message": "WhatsApp backend is healthy"}), 200

@app.route('/', methods=['GET', 'HEAD'])
def root():
    """Root endpoint for health checks."""
    return jsonify({"status": "ok", "message": "Narayan Shiva Sansthan WhatsApp Service"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4000, debug=False)
