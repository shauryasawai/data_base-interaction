from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from django.conf import settings
import pandas as pd
import openpyxl
from io import BytesIO
from .models import Lead, UploadHistory
from .forms import LeadUploadForm, LeadSearchForm, LeadForm
import re
from collections import Counter
from openai import OpenAI
import json


def home(request):
    """Home page with upload and search functionality"""
    upload_form = LeadUploadForm()
    search_form = LeadSearchForm()
    leads = Lead.objects.all()[:1000]  # Show recent 1000 leads
    
    context = {
        'upload_form': upload_form,
        'search_form': search_form,
        'leads': leads,
        'total_leads': Lead.objects.count()
    }
    return render(request, 'leads/home.html', context)


def upload_leads(request):
    if request.method != 'POST':
        return redirect('home')

    form = LeadUploadForm(request.POST, request.FILES)

    if not form.is_valid():
        messages.error(request, "Invalid upload form")
        return redirect('home')

    excel_file = request.FILES['file']

    try:
        df = pd.read_excel(excel_file)

        # Column mapping from Excel to Lead model
        column_mapping = {
            'Name': 'name',
            'Linkedin Link': 'linkedin_url',
            'Designation': 'role',
            'Linkedin About': 'notes',
            'Company Name': 'company',
            'Location\n(Where GCC center is opening.\nIf 2 locations, one is HQ one is GCC)': 'location',
            'Company Headquarters': 'company_hq',
            'Category': 'category',
            'Expansion Type': 'expansion_type',
            'Comments': 'comments',
            'Email': 'email',
            'Phone': 'phone',
            'Category\n(By level of relationship)': 'relationship_category',
            'Message, invite sent for lead generation only (Yes/No/Doubtful)': 'invite_sent',
            'MB Connection Level': 'connection_level',
            'Relevant': 'relevant',
            'Phone Number sent to sir': 'phone_sent',
            'Response': 'response',
            'Remarks': 'remarks',
            'Original Sheet': 'original_sheet'
        }

        # Rename columns
        df = df.rename(columns=column_mapping)

        # Check if 'name' column exists after mapping
        if 'name' not in df.columns:
            messages.error(request, "Excel must contain a 'Name' column")
            return redirect('home')

        imported = 0
        updated = 0
        skipped = 0

        for idx, row in df.iterrows():
            # Get name - skip if empty
            name = str(row.get('name', '')).strip()
            if not name or name == 'nan':
                skipped += 1
                continue

            # Get email - generate if missing
            email = row.get('email')
            if pd.notna(email) and str(email).strip() and str(email).strip().lower() != 'nan':
                email = str(email).strip()
            else:
                # Auto-generate email if missing
                email = f"{name.lower().replace(' ', '.')}.{idx}@leads.local"

            # Helper function to safely get string values
            def safe_str(value, default=''):
                if pd.notna(value) and str(value).strip() and str(value).strip().lower() != 'nan':
                    return str(value).strip()
                return default

            # Prepare lead data with all mapped fields
            lead_data = {
                'name': name,
                'email': email,
                'phone': safe_str(row.get('phone')),
                'role': safe_str(row.get('role')),
                'company': safe_str(row.get('company')),
                'linkedin_url': safe_str(row.get('linkedin_url')),
                'location': safe_str(row.get('location')),
                'skills': '',
                'experience_years': 0,
                'notes': safe_str(row.get('notes')),
            }

            # Create or update lead
            lead, created = Lead.objects.update_or_create(
                email=email,
                defaults=lead_data
            )

            if created:
                imported += 1
            else:
                updated += 1

        # Create upload history record
        UploadHistory.objects.create(
            filename=excel_file.name,
            records_imported=imported,
            records_updated=updated
        )

        # Success message
        message_parts = [f"Imported {imported} new leads, updated {updated} existing leads"]
        if skipped > 0:
            message_parts.append(f"skipped {skipped} empty rows")
        
        messages.success(request, ", ".join(message_parts))

    except Exception as e:
        messages.error(request, f"Upload failed: {str(e)}")

    return redirect('home')


def normalize_text(text):
    """Normalize text for matching"""
    if not text:
        return []
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    return [t for t in text.split() if len(t) > 2]


def search_leads(request):
    if request.method != 'POST':
        return redirect('home')

    query_text = request.POST.get('skills', '').strip()
    if not query_text:
        return redirect('home')

    query_tokens = normalize_text(query_text)
    query_set = set(query_tokens)
    query_counter = Counter(query_tokens)

    leads = Lead.objects.all()
    matched_leads = []
    
    # Track keyword statistics
    matched_keywords = Counter()

    for lead in leads:
        score = 0
        include = False
        match_context = []

        # Normalize lead fields
        role_tokens = normalize_text(lead.role)
        company_tokens = normalize_text(lead.company)
        skills_tokens = normalize_text(lead.skills)
        notes_tokens = normalize_text(lead.notes)
        location_tokens = normalize_text(lead.location)

        # --- Role match ---
        role_match = set(role_tokens) & query_set
        if role_match:
            score += 30 + 5 * len(role_match)
            include = True
            matched_keywords.update(role_match)
            match_context.append(f"Role: {', '.join(role_match)}")

        # --- Skills match ---
        skills_match = set(skills_tokens) & query_set
        if skills_match:
            score += 40 + 5 * len(skills_match)
            include = True
            matched_keywords.update(skills_match)
            match_context.append(f"Skills: {', '.join(skills_match)}")

        # --- Company match ---
        company_match = set(company_tokens) & query_set
        if company_match:
            score += 25
            include = True
            matched_keywords.update(company_match)
            match_context.append(f"Company: {', '.join(company_match)}")

        # --- Location match ---
        location_match = set(location_tokens) & query_set
        if location_match:
            score += 15
            include = True
            matched_keywords.update(location_match)
            match_context.append(f"Location: {', '.join(location_match)}")

        # --- Notes overlap ---
        misc_overlap = set(notes_tokens) & query_set
        if misc_overlap:
            score += 10
            include = True
            matched_keywords.update(misc_overlap)
            match_context.append(f"Notes: {', '.join(misc_overlap)}")

        # Normalize score
        score = min(score, 100)

        if include:
            lead.match_score = score
            lead.match_context = match_context
            lead.save(update_fields=['match_score'])
            matched_leads.append(lead)

    # Sort by match score
    matched_leads.sort(key=lambda x: x.match_score, reverse=True)

    # Calculate keyword statistics
    matched_keywords_list = [
        {'word': word, 'count': count} 
        for word, count in matched_keywords.most_common()
    ]
    
    # Find missing keywords
    missing_keywords = query_set - set(matched_keywords.keys())
    
    # Find common keywords in results (partial matches)
    all_db_keywords = Counter()
    for lead in matched_leads[:20]:
        all_db_keywords.update(normalize_text(lead.role))
        all_db_keywords.update(normalize_text(lead.company))
        all_db_keywords.update(normalize_text(lead.location))
    
    partial_keywords = []
    for word, count in all_db_keywords.most_common(10):
        if word not in query_set and count > 2:
            partial_keywords.append({'word': word, 'count': count})
    
    # Calculate match rate
    match_rate = 0
    if query_tokens:
        match_rate = round((len(matched_keywords) / len(query_set)) * 100, 1)

    keyword_stats = {
        'matched': matched_keywords_list,
        'missing': sorted(list(missing_keywords)),
        'partial': partial_keywords[:5],
        'match_rate': match_rate
    }

    return render(
        request,
        'leads/search_results.html',
        {
            'leads': matched_leads,
            'query': query_text,
            'keyword_stats': keyword_stats,
            'mode': 'generalized_match'
        }
    )


def truncate_text(text, max_length=100):
    """Truncate text to maximum length"""
    if not text:
        return ""
    text = str(text).strip()
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text


def get_industry_distribution(leads):
    """
    Get distribution of leads across different industries/domains
    Returns top 5 industries with counts and percentages
    """
    industry_counter = Counter()
    total = leads.count()
    
    if total == 0:
        return []
    
    for lead in leads:
        industry = infer_industry(lead.role, lead.company, lead.notes)
        industry_counter[industry] += 1
    
    # Format the results with percentages - TOP 5 ONLY
    industry_stats = []
    for industry, count in industry_counter.most_common(5):  # Limited to top 5
        percentage = round((count / total) * 100, 1)
        industry_stats.append({
            'name': industry.replace('_', ' ').title(),
            'count': count,
            'percentage': percentage
        })
    
    return industry_stats


def ai_lead_generation(request):
    """
    AI-powered lead generation using OpenAI to understand user intent
    and match against leads semantically
    """
    if request.method != 'POST':
        # Get industry distribution for overview
        all_leads = Lead.objects.all()
        industry_stats = get_industry_distribution(all_leads)
        
        return render(request, 'leads/ai_lead_generation.html', {
            'total_leads': Lead.objects.count(),
            'industry_stats': industry_stats
        })
    
    user_prompt = request.POST.get('prompt', '').strip()
    
    if not user_prompt:
        messages.error(request, "Please enter a description of what you're looking for")
        all_leads = Lead.objects.all()
        industry_stats = get_industry_distribution(all_leads)
        return render(request, 'leads/ai_lead_generation.html', {
            'total_leads': Lead.objects.count(),
            'industry_stats': industry_stats
        })
    
    try:
        # Initialize OpenAI client (v1.0+ API)
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
        # Get all leads
        all_leads = Lead.objects.all()
        
        if not all_leads.exists():
            messages.warning(request, "No leads found in database")
            return render(request, 'leads/ai_lead_generation.html', {
                'total_leads': 0,
                'user_prompt': user_prompt,
                'industry_stats': []
            })
        
        # Analyze database composition for industry insights
        industry_analysis = analyze_database_composition(all_leads)
        
        # OPTIMIZED: Limit to 150 leads and truncate long fields
        # This keeps us well under the 16K token limit
        leads_data = []
        for lead in all_leads[:150]:  # Reduced from 500 to 150
            leads_data.append({
                'id': lead.id,
                'name': truncate_text(lead.name, 50),
                'role': truncate_text(lead.role, 60),
                'company': truncate_text(lead.company, 50),
                'location': truncate_text(lead.location, 40),
                'skills': truncate_text(lead.skills, 80),
                # Removed notes and experience_years to save tokens
            })
        
        # Create OPTIMIZED AI prompt (much shorter)
        system_prompt = """You are a lead matching expert. Analyze the user's request and match it with leads from the database.

Consider:
1. Supplier/vendor or consumer/client need
2. Role relevance (40 points)
3. Company/industry match (30 points)
4. Skills alignment (20 points)
5. Location match (10 points)

Return JSON:
{
    "interpretation": "brief understanding",
    "search_type": "supplier or consumer",
    "industry_alignment": "brief alignment note",
    "matches": [
        {
            "lead_id": int,
            "confidence_score": int,
            "reasoning": "brief why",
            "strengths": ["strength1", "strength2"],
            "concerns": ["concern1"] or []
        }
    ]
}

Only leads with score >= 50. Top 20 matches max."""

        # Simplified database insights
        db_summary = {
            'total': industry_analysis['total_leads'],
            'top_roles': list(industry_analysis['top_roles'].keys())[:5],
            'top_industries': list(industry_analysis['industries_represented'].keys())[:5]
        }

        user_message = f"""User Request: {user_prompt}

Database Summary: {json.dumps(db_summary)}

Leads (ID, Name, Role, Company, Location, Skills):
{json.dumps(leads_data, indent=1)}

Return best matches in JSON format."""

        # Call OpenAI API with reduced context
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.3,
            max_tokens=1500  # Reduced from 2000
        )
        
        # Parse AI response
        ai_response_text = response.choices[0].message.content
        
        # Clean the response (remove markdown code blocks if present)
        ai_response_text = ai_response_text.strip()
        if ai_response_text.startswith('```json'):
            ai_response_text = ai_response_text[7:]
        if ai_response_text.startswith('```'):
            ai_response_text = ai_response_text[3:]
        if ai_response_text.endswith('```'):
            ai_response_text = ai_response_text[:-3]
        ai_response_text = ai_response_text.strip()
        
        ai_result = json.loads(ai_response_text)
        
        # Retrieve matched leads from database
        matched_leads = []
        for match in ai_result.get('matches', []):
            try:
                lead = Lead.objects.get(id=match['lead_id'])
                lead.ai_confidence_score = match['confidence_score']
                lead.ai_reasoning = match['reasoning']
                lead.ai_strengths = match.get('strengths', [])
                lead.ai_concerns = match.get('concerns', [])
                matched_leads.append(lead)
            except Lead.DoesNotExist:
                continue
        
        context = {
            'leads': matched_leads,
            'user_prompt': user_prompt,
            'interpretation': ai_result.get('interpretation', ''),
            'search_type': ai_result.get('search_type', ''),
            'industry_alignment': ai_result.get('industry_alignment', ''),
            'total_leads': Lead.objects.count(),
            'analyzed_leads': 150,  # Show user how many were analyzed
            'database_insights': industry_analysis,
            'mode': 'ai_powered'
        }
        
        return render(request, 'leads/ai_lead_results.html', context)
        
    except Exception as e:
        # Handle different types of errors
        error_message = str(e)
        
        all_leads = Lead.objects.all()
        industry_stats = get_industry_distribution(all_leads)
        
        if "api_key" in error_message.lower() or "authentication" in error_message.lower():
            messages.error(request, "OpenAI API key is invalid. Please check your settings.")
        elif "rate_limit" in error_message.lower():
            messages.error(request, "OpenAI API rate limit reached. Please try again later.")
        elif "context_length_exceeded" in error_message.lower():
            messages.error(request, "Too much data to process. Try being more specific in your search.")
        elif "json" in error_message.lower():
            messages.error(request, f"Error parsing AI response. Please try again.")
        else:
            messages.error(request, f"AI lead generation failed: {error_message}")
        
        return render(request, 'leads/ai_lead_generation.html', {
            'total_leads': Lead.objects.count(),
            'user_prompt': user_prompt,
            'industry_stats': industry_stats
        })


def analyze_database_composition(leads):
    """
    Analyze the database to understand which industries/sectors are well-represented
    This helps the AI provide better context about match confidence
    """
    analysis = {
        'total_leads': leads.count(),
        'top_roles': Counter(),
        'top_companies': Counter(),
        'top_locations': Counter(),
        'industries_represented': Counter()
    }
    
    for lead in leads:
        # Count roles
        if lead.role:
            analysis['top_roles'][lead.role.lower()] += 1
        
        # Count companies
        if lead.company:
            analysis['top_companies'][lead.company.lower()] += 1
        
        # Count locations
        if lead.location:
            analysis['top_locations'][lead.location.lower()] += 1
        
        # Infer industry from company/role
        industry = infer_industry(lead.role, lead.company, lead.notes)
        if industry:
            analysis['industries_represented'][industry] += 1
    
    # Convert to serializable format
    return {
        'total_leads': analysis['total_leads'],
        'top_roles': dict(analysis['top_roles'].most_common(10)),
        'top_companies': dict(analysis['top_companies'].most_common(10)),
        'top_locations': dict(analysis['top_locations'].most_common(10)),
        'industries_represented': dict(analysis['industries_represented'].most_common(10))
    }


def infer_industry(role, company, notes):
    """
    Infer industry sector from role, company name, and notes
    """
    text = f"{role} {company} {notes}".lower()
    
    industry_keywords = {
        'technology': ['software', 'tech', 'it', 'developer', 'engineer', 'data', 'ai', 'cloud', 'saas', 'digital', 'cyber', 'programming', 'coding'],
        'finance': ['finance', 'bank', 'investment', 'trading', 'accounting', 'fintech', 'financial', 'capital', 'wealth', 'credit'],
        'healthcare': ['healthcare', 'medical', 'pharma', 'hospital', 'clinical', 'health', 'biotech', 'medicine', 'pharmaceutical'],
        'manufacturing': ['manufacturing', 'production', 'factory', 'industrial', 'assembly', 'supply chain', 'operations'],
        'retail': ['retail', 'ecommerce', 'store', 'shop', 'merchant', 'consumer', 'sales'],
        'consulting': ['consulting', 'consultant', 'advisory', 'strategy', 'management consulting'],
        'real_estate': ['real estate', 'property', 'construction', 'building', 'infrastructure'],
        'education': ['education', 'university', 'school', 'training', 'learning', 'academic', 'teaching'],
        'energy': ['energy', 'oil', 'gas', 'renewable', 'power', 'utilities', 'solar', 'wind'],
        'telecommunications': ['telecom', 'network', 'wireless', 'broadband', 'communication', '5g'],
        'media': ['media', 'advertising', 'marketing', 'content', 'publishing', 'broadcasting'],
        'automotive': ['automotive', 'automobile', 'vehicle', 'car', 'transportation'],
        'aerospace': ['aerospace', 'aviation', 'aircraft', 'defense'],
        'logistics': ['logistics', 'shipping', 'freight', 'delivery', 'warehouse', 'distribution'],
        'hospitality': ['hospitality', 'hotel', 'restaurant', 'tourism', 'travel'],
        'legal': ['legal', 'law', 'attorney', 'lawyer', 'compliance'],
        'insurance': ['insurance', 'underwriting', 'risk', 'claims'],
        'agriculture': ['agriculture', 'farming', 'agribusiness', 'agro'],
        'gaming': ['gaming', 'game', 'esports', 'entertainment'],
        'government': ['government', 'public sector', 'municipal', 'federal', 'state']
    }
    
    for industry, keywords in industry_keywords.items():
        if any(keyword in text for keyword in keywords):
            return industry
    
    return 'other'


def lead_detail(request, pk):
    """View and edit individual lead"""
    lead = get_object_or_404(Lead, pk=pk)
    
    if request.method == 'POST':
        form = LeadForm(request.POST, instance=lead)
        if form.is_valid():
            form.save()
            messages.success(request, "Lead updated successfully!")
            return redirect('lead_detail', pk=pk)
    else:
        form = LeadForm(instance=lead)
    
    context = {
        'lead': lead,
        'form': form
    }
    return render(request, 'leads/lead_detail.html', context)


def delete_lead(request, pk):
    """Delete a lead"""
    lead = get_object_or_404(Lead, pk=pk)
    lead.delete()
    messages.success(request, "Lead deleted successfully!")
    return redirect('home')


def export_leads(request):
    """Export all leads to Excel"""
    leads = Lead.objects.all()
    
    # Create DataFrame
    data = []
    for lead in leads:
        data.append({
            'name': lead.name,
            'role': lead.role,
            'company': lead.company,
            'linkedin_url': lead.linkedin_url,
            'location': lead.location,
            'email': lead.email,
            'phone': lead.phone,
            'skills': lead.skills,
            'experience_years': lead.experience_years,
            'notes': lead.notes,
            'match_score': lead.match_score,
        })
    
    df = pd.DataFrame(data)
    
    # Create Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Leads')
    
    output.seek(0)
    
    # Create response
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=leads_export.xlsx'
    
    return response


def clear_chat_history(request, pk):
    """Clear chat history for a specific lead"""
    if request.method == 'POST' or request.method == 'GET':
        history_key = f'chat_history_{pk}'
        if history_key in request.session:
            del request.session[history_key]
            request.session.modified = True
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Chat history cleared'})
        else:
            messages.success(request, 'Chat history cleared successfully!')
            return redirect('all_leads', pk=pk)
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=400)


def all_leads(request):
    leads = Lead.objects.all()
    search_query = request.GET.get('search', '').strip()

    if search_query:
        leads = leads.filter(
            Q(name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(company__icontains=search_query) |
            Q(skills__icontains=search_query)
        )

    context = {
        'leads': leads,
        'search_query': search_query,
        'upload_form': LeadUploadForm(),
        'search_form': LeadSearchForm(),
    }

    return render(request, 'leads/all_leads.html', context)


def prompt_builder(request):
    """
    Guided prompt builder for AI lead generation
    Helps users create effective search prompts step-by-step
    """
    return render(request, 'leads/prompt_builder.html')