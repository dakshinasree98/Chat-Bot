import streamlit as st
import os
import re
import random
from datetime import datetime, timedelta
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv() 

# Set up Gemini API key from .env file
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
)

# Expanded dummy donation data with more realistic information
DUMMY_DONATIONS = {
    1: [
        {"amount": 3000, "date": "2025-03-02", "utr": "UTR789456", "receipt_sent": False, "donor_name": "Rajesh Sharma", "payment_method": "UPI", "campaign": "Education Fund"},
        {"amount": 5000, "date": "2024-12-15", "utr": "UTR123789", "receipt_sent": True, "donor_name": "Rajesh Sharma", "payment_method": "Bank Transfer", "campaign": "Winter Relief"}
    ],
    2: [
        {"amount": 10000, "date": "2025-04-01", "utr": "UTR456123", "receipt_sent": True, "donor_name": "Priya Patel", "payment_method": "Credit Card", "campaign": "Healthcare Initiative"},
        {"amount": 2500, "date": "2025-01-10", "utr": "UTR987234", "receipt_sent": True, "donor_name": "Priya Patel", "payment_method": "UPI", "campaign": "Education Fund"}
    ],
    3: [
        {"amount": 50000, "date": "2025-03-15", "utr": "UTR567890", "receipt_sent": False, "donor_name": "Amit Verma", "payment_method": "Bank Transfer", "campaign": "Rural Development"},
        {"amount": 15000, "date": "2024-11-05", "utr": "UTR345678", "receipt_sent": True, "donor_name": "Amit Verma", "payment_method": "UPI", "campaign": "Clean Water Project"}
    ],
    4: [
        {"amount": 1000, "date": "2025-03-28", "utr": "UTR654321", "receipt_sent": True, "donor_name": "Sneha Gupta", "payment_method": "UPI", "campaign": "Education Fund"}
    ],
    5: [],  # New donor with no history
    6: [
        {"amount": 2000, "date": "2025-02-18", "utr": "UTR123456", "receipt_sent": True, "donor_name": "Arvin Kumar", "payment_method": "UPI", "campaign": "Education Fund"}
    ]
}

# Phone numbers for dummy data
DONOR_PHONE_NUMBERS = {
    1: "+91 98765 43210",
    2: "+91 87654 32109",
    3: "+91 76543 21098",
    4: "+91 65432 10987",
    5: "+91 54321 09876",
    6: "+91 97800 86800"
}

# Email addresses for dummy data
DONOR_EMAILS = {
    1: "rajesh.sharma@example.com",
    2: "priya.patel@example.com",
    3: "amit.verma@example.com",
    4: "sneha.gupta@example.com",
    5: "new.donor@example.com",
    6: "arvin.kumar@example.com"
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

def get_user_id_from_info(extracted_info):
    # Determine user ID from extracted information
    if extracted_info["utr"]:
        for id, donations in DUMMY_DONATIONS.items():
            if any(d.get("utr", "") == extracted_info["utr"] for d in donations):
                return id
    
    # If no UTR match, try to match by name
    if extracted_info["name"]:
        for id, donations in DUMMY_DONATIONS.items():
            if donations and any(extracted_info["name"].lower() in d.get("donor_name", "").lower() for d in donations):
                return id
    
    # Check if the phone number corresponds to any donor
    if extracted_info["phone"]:
        for id, phone in DONOR_PHONE_NUMBERS.items():
            if extracted_info["phone"] in phone.replace(" ", ""):
                return id
    
    # Special case for Arvin
    if extracted_info["name"] == "Arvin" or (extracted_info["phone"] and "97800" in extracted_info["phone"]):
        return 6
    
    # Default to user 1 or a random user
    return random.choice([1, 2, 3, 4])

def generate_response(query, history=None):
    model = "gemini-2.0-flash"

    # Extract information and identify intent
    extracted_info = extract_info_from_query(query)
    intent = identify_intent(query)
    st.session_state.last_intent = intent
    
    # Determine user ID
    user_id = get_user_id_from_info(extracted_info)
    
    # Build user context with detailed information
    if user_id in DUMMY_DONATIONS and DUMMY_DONATIONS[user_id]:
        user_context = f"\nDonor Information:\nName: {DUMMY_DONATIONS[user_id][0].get('donor_name')}\nPhone: {DONOR_PHONE_NUMBERS.get(user_id)}\nEmail: {DONOR_EMAILS.get(user_id)}\n\nDonation History:\n"
        for d in DUMMY_DONATIONS[user_id]:
            receipt_status = "Sent on " + (datetime.strptime(d.get('date'), "%Y-%m-%d") + timedelta(days=2)).strftime("%Y-%m-%d") if d.get("receipt_sent") else "Pending - Will be sent within 24 hours"
            user_context += f"- ₹{d.get('amount')} on {d.get('date')} for {d.get('campaign')}, via {d.get('payment_method')}, UTR: {d.get('utr')}, Receipt Status: {receipt_status}\n"
    else:
        user_context = "\nThis appears to be a new donor with no previous donation history in our system.\n"
    
    # Add current date and time context
    current_datetime = datetime.now().strftime("%Y-%m-%d, %A, %H:%M")
    time_context = f"\nCurrent Date and Time: {current_datetime}\nOffice Hours: {OFFICE_HOURS}\nActive Campaigns: {', '.join(CURRENT_CAMPAIGNS)}\n"

    # Initial message handling
    if not history:
        system_instruction = f"""You are Ananya, a friendly and helpful receptionist at Narayan Shiva Sansthan, a charitable organization.
Your role is to assist donors, potential donors, and anyone with inquiries about the foundation.
Always be warm, personable, and speak as if you're sitting at the front desk of our charity office.

Use Indian expressions and references where appropriate. Address people respectfully, using "ji" occasionally.
If the conversation is in Hindi or any regional language, respond accordingly.

Current information:
{time_context}

Donor information:
{user_context}

Foundation information:
{LONG_CONTEXT}

When greeting callers:
- Use phrases like "Namaste", "Good morning/afternoon", or "Welcome to Narayan Shiva Sansthan"
- Introduce yourself as Ananya from the reception desk
- Thank donors for their support and generosity

IMPORTANT: Never include any "acting" or roleplay elements in your responses. Do not include phrases like "(slight pause)" or descriptions of your actions. Simply respond as if you're having a natural conversation.

Guidelines based on inquiry type:
1. For donation intents - Express gratitude, provide donation options, and the donation link (https://donate.narayanss.org)
2. For receipt issues - Check the donation history, apologize for any delays, and offer to expedite
3. For UTR verifications - Confirm transactions from the donation history if available
4. For volunteer inquiries - Share volunteer opportunities and ask for their areas of interest
5. For tax benefit inquiries - Explain Section 80G benefits clearly and what documentation we provide
6. For office inquiries - Share our address and invite them to visit during office hours
7. For project inquiries - Describe our current initiatives with enthusiasm and share success stories

Important notes:
- Be compassionate and patient, especially with donation-related concerns
- If you don't have certain information, offer to connect them with the appropriate team member
- Always express gratitude for their interest in our foundation
- End conversations warmly and ask if there's anything else you can assist with
- Your responses should be concise and professional

Remember, you're the friendly face of Narayan Shiva Sansthan Foundation!
"""

        generate_config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.7,  # Slightly higher temperature for more personable responses
            max_output_tokens=8000,
        )

        contents = [query]
        full_response = ""

        for chunk in client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=generate_config
        ):
            text = chunk.text or ""
            full_response += text
            yield text

        yield full_response, [
            {"role": "user", "content": query},
            {"role": "assistant", "content": full_response}
        ]

    else:
        # Continuation from chat history with updated context
        # Modified to properly use Gemini API without 'role' parameter
        
        # Create content with system instructions for context
        system_content = f"""You are Ananya, a friendly and helpful receptionist at Narayan Shiva Sansthan Foundation.
Continue the conversation naturally as if you're speaking from the reception desk.

Current information:
{time_context}

Donor information:
{user_context}

IMPORTANT: Never include any "acting" or roleplay elements in your responses. Do not include phrases like "(slight pause)" or descriptions of your actions. Simply respond as if you're having a natural conversation.

Remember to be warm, personable, and helpful while maintaining the professional tone of a charity organization.
"""
        
        # Initialize the chat
        chat = client.chats.create(model=model)
        
        # Add the system instruction using a system message format instead
        chat.send_message(system_content)
        
        # Add the conversation history
        for msg in history:
            if msg.get("role") == "user":
                chat.send_message(msg.get("content", ""))
        
        # Send the current query and stream the response
        response_stream = chat.send_message_stream(query)
        full_response = ""

        for chunk in response_stream:
            text = chunk.text or ""
            full_response += text
            yield text

        updated_history = history.copy()
        updated_history.append({"role": "user", "content": query})
        updated_history.append({"role": "assistant", "content": full_response})

        yield full_response, updated_history

# ---- Streamlit UI ----

st.set_page_config(page_title="Narayan Shiva Sansthan Foundation", page_icon="🤲")
st.title("🤲 Narayan Shiva Sansthan Foundation")
st.subheader("Donor Assistance Portal")
st.write("Welcome! I'm Ananya from Narayan Shiva Sansthan. How may I assist you with your donation or inquiry today?")

# Initialize session state
if "chat_history" not in st.session_state or not isinstance(st.session_state.chat_history, list):
    st.session_state.chat_history = []

if "last_intent" not in st.session_state:
    st.session_state.last_intent = None

# Display chat history
for message in st.session_state.chat_history:
    if isinstance(message, dict):
        role = message.get("role", "user")
        content = message.get("content", "")
        avatar = "👤" if role == "user" else "🤲"
        with st.chat_message(role, avatar=avatar):
            st.write(content)

# User input
user_query = st.chat_input("Type your message...")

if user_query:
    with st.chat_message("user", avatar="👤"):
        st.write(user_query)

    with st.chat_message("assistant", avatar="🤲"):
        response_placeholder = st.empty()
        full_response = ""
        response_generator = generate_response(
            user_query,
            history=st.session_state.chat_history
        )

        try:
            for chunk in response_generator:
                if isinstance(chunk, str):
                    full_response += chunk
                    response_placeholder.markdown(full_response)
                elif isinstance(chunk, tuple):
                    full_response, updated_history = chunk
                    st.session_state.chat_history = updated_history
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
            fallback = "Namaste! I apologize for the technical difficulty. Could you please repeat your question or maybe call our helpdesk at +91 88888-55555? I'd be happy to assist you further."
            st.session_state.chat_history.append({"role": "user", "content": user_query})
            st.session_state.chat_history.append({"role": "assistant", "content": fallback})
            response_placeholder.write(fallback)

# Sidebar with quick actions
with st.sidebar:
    st.header("Quick Actions")
    if st.button("✨ Make a Donation"):
        st.session_state.chat_history.append({"role": "user", "content": "I'd like to make a donation."})
        st.rerun()
    if st.button("🧾 Check Receipt Status"):
        st.session_state.chat_history.append({"role": "user", "content": "I haven't received my donation receipt yet."})
        st.rerun()
    if st.button("🤝 Volunteer Opportunities"):
        st.session_state.chat_history.append({"role": "user", "content": "How can I volunteer with your organization?"})
        st.rerun()
    if st.button("📍 Office Location"):
        st.session_state.chat_history.append({"role": "user", "content": "Where is your office located?"})
        st.rerun()
    
    st.divider()
    
    # Clear conversation
    if st.button("🗑️ Clear Conversation"):
        st.session_state.chat_history = []
        st.rerun()
