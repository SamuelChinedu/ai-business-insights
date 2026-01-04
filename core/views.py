# Create your views here.
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Analysis
import pandas as pd
from sklearn.linear_model import LinearRegression
import numpy as np
import hashlib
from django.contrib.auth import logout as auth_logout
from django.http import JsonResponse
import easyocr
import tempfile
import os
from PIL import Image
import io
from datetime import timedelta
import uuid
from django.core.files.storage import default_storage
from.models import User
from .models import Profile
from django.core.files import File
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from django.http import HttpResponse
from io import BytesIO


def home(request):
    return render(request, 'home.html')

def user_login(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('dashboard')
        messages.error(request, 'Invalid credentials')
    return render(request, 'login.html')

def register(request):
    if request.method == 'POST':
        username = request.POST['username']
        email = request.POST['email']
        password = request.POST['password']
        business_name = request.POST['business_name']
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already taken')
        elif User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered')
        else:
            # Create user
            user = User.objects.create_user(username=username, email=email, password=password)
            
            # Create or update profile safely
            profile, created = Profile.objects.get_or_create(user=user)
            profile.business_name = business_name
            profile.save()
            
            login(request, user)
            messages.success(request, 'Account created successfully! Welcome to your dashboard.')
            return redirect('dashboard')
    
    return render(request, 'register.html')
@login_required
def dashboard(request):
    analyses = Analysis.objects.filter(user=request.user).order_by('-created_at')
    context = {'analyses': analyses, 'has_data': analyses.exists()}
    return render(request, 'dashboard.html', context)



# Temporary storage for preview
TEMP_UPLOADS = {}

@login_required
def upload_file(request):
    if request.method == 'POST':
        file = request.FILES['file']
        business_type = request.POST['business_type']
        
        # Save file temporarily
        file_id = str(uuid.uuid4())
        file_path = default_storage.save(f'temp/{file_id}_{file.name}', file)
        
        # Read preview
        try:
            if file.name.endswith('.csv'):
                df = pd.read_csv(default_storage.path(file_path))
            else:
                df = pd.read_excel(default_storage.path(file_path))
        except:
            messages.error(request, "Could not read file")
            return redirect('dashboard')
        
        preview = df.head(10).to_html(classes='table table-striped', index=False)
        columns = list(df.columns)
        
        # Save in session-like dict
        TEMP_UPLOADS[request.user.id] = {
            'file_path': file_path,
            'columns': columns,
            'business_type': business_type
        }
        
        return render(request, 'column_mapping.html', {
            'preview': preview,
            'columns': columns,
            'business_type': business_type,
            'file_id': file_id
        })
    
    return redirect('dashboard')


@login_required
def process_with_mapping(request):
    if request.method == 'POST':
        user_id = request.user.id
        if user_id not in TEMP_UPLOADS:
            messages.error(request, "Session expired — please upload again")
            return redirect('dashboard')
        
        temp_data = TEMP_UPLOADS[user_id]
        file_path = temp_data['file_path']
        business_type = temp_data['business_type']
        
        # Get user selections
        date_col = request.POST['date_column']
        revenue_col = request.POST['revenue_column']
        item_col = request.POST.get('item_column', '')  # optional
        
        # Read full file
        try:
            if file_path.endswith('.csv'):
                df = pd.read_csv(default_storage.path(file_path))
            else:
                df = pd.read_excel(default_storage.path(file_path))
        except Exception as e:
            messages.error(request, f"Error reading file: {str(e)}")
            return redirect('dashboard')
        
        # Rename selected columns
        rename_map = {}
        if date_col: rename_map[date_col] = 'Date'
        if revenue_col: rename_map[revenue_col] = 'revenue'
        if item_col: rename_map[item_col] = 'item'
        
        df = df.rename(columns=rename_map)
        
        # Validate required columns
        if 'Date' not in df.columns or 'revenue' not in df.columns:
            messages.error(request, "Please select Date and Revenue columns")
            return render(request, 'column_mapping.html', {
                'preview': df.head(10).to_html(classes='table table-striped', index=False),
                'columns': list(df.columns),
                'business_type': business_type,
                'error': 'Missing required columns'
            })
        
        # Analysis code (same as before)
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date'])
        
        daily = df.groupby('Date')['revenue'].sum().reset_index()
        
        total_revenue = float(df['revenue'].sum())
        total_transactions = int(len(df))
        avg_daily = float(daily['revenue'].mean())
        growth = float(daily['revenue'].pct_change().mean() * 100) if len(daily) > 1 else 0.0
        
        top_col = 'item' if 'item' in df.columns else df.columns[2]
        top = df.groupby(top_col)['revenue'].sum().nlargest(5)
        top_names = top.index.astype(str).tolist()
        top_values = [float(x) for x in top.values.tolist()]
        
        df['Day'] = df['Date'].dt.day_name()
        busy = df.groupby('Day')['revenue'].sum().reindex([
            'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'
        ])
        busy_days = busy.index.tolist()
        busy_values = [float(x) if pd.notna(x) else 0 for x in busy.values.tolist()]
        
        daily_sorted = daily.sort_values('Date')
        X = np.arange(len(daily_sorted)).reshape(-1, 1)
        y = daily_sorted['revenue'].values
        model = LinearRegression().fit(X, y)
        future_X = np.arange(len(daily_sorted), len(daily_sorted) + 7).reshape(-1, 1)
        pred = model.predict(future_X)
        
        last_date = daily_sorted['Date'].iloc[-1]
        forecast_dates = [(last_date + timedelta(days=i+1)).strftime('%Y-%m-%d') for i in range(7)]
        forecast_values = [float(x) for x in pred.tolist()]
        
        historical_dates = daily_sorted['Date'].astype(str).tolist()
        historical_revenue = [float(x) for x in daily_sorted['revenue'].tolist()]
        
        daily_dates = daily['Date'].astype(str).tolist()
        daily_revenue = [float(x) for x in daily['revenue'].tolist()]
        
        data_hash = hashlib.sha256(pd.util.hash_pandas_object(df).values).hexdigest()
        
        summary = {
            'total_revenue': total_revenue,
            'transactions': total_transactions,
            'avg_daily': avg_daily,
            'growth': growth,
            'chart_data': {
                'daily_dates': daily_dates,
                'daily_revenue': daily_revenue,
                'top_names': top_names,
                'top_values': top_values,
                'busy_days': busy_days,
                'busy_values': busy_values,
                'historical_dates': historical_dates,
                'historical_revenue': historical_revenue,
                'forecast_dates': forecast_dates,
                'forecast_values': forecast_values,
            }
        }
        
        # Get title from form
        title = request.POST.get('title', 'Untitled Analysis')

        # Save original uploaded file for admin
        from django.core.files.base import ContentFile
        import os

        file_name = os.path.basename(file_path)
        try:
            with default_storage.open(file_path, 'rb') as uploaded_file:
                file_content = uploaded_file.read()
            saved_file = ContentFile(file_content, name=file_name)
        except:
            saved_file = None  # fallback if error

        # Create analysis
        Analysis.objects.create(
            user=request.user,
            business_type=business_type,
            data_summary=summary,
            raw_data_hash=data_hash,
            title=title,
            uploaded_file=saved_file
        )
        
        # Clean up temp file
        default_storage.delete(file_path)
        del TEMP_UPLOADS[user_id]
        
        messages.success(request, "Custom analysis completed successfully!")
        return redirect('dashboard')
    
    return redirect('dashboard')    
def user_logout(request):
    auth_logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('home')

@login_required
def ocr_process(request):
    if request.method == 'POST' and 'photo' in request.FILES:
        photo = request.FILES['photo']
        
        # Save temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
            for chunk in photo.chunks():
                tmp_file.write(chunk)
            tmp_path = tmp_file.name
        
        try:
            # Run OCR
            result = reader.readtext(tmp_path)
            extracted_text = "\n".join([text for (_, text, _) in result])
            
            # Clean up
            os.unlink(tmp_path)
            
            return JsonResponse({'success': True, 'text': extracted_text})
        except Exception as e:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'No photo uploaded'})


@login_required
def analysis_detail(request, pk):
    analysis = Analysis.objects.get(pk=pk, user=request.user)
    summary = analysis.data_summary
    chart_data = summary.get('chart_data', {})
    
    # Existing calculations...
    busiest_value = 0
    busiest_percentage = 0.0
    if chart_data.get('busy_values'):
        busiest_value = chart_data['busy_values'][0] if chart_data['busy_values'] else 0
        total_revenue = summary.get('total_revenue', 1)
        if total_revenue > 0:
            busiest_percentage = round((busiest_value / total_revenue) * 100, 1)
    
    top_item_name = chart_data.get('top_names', ['N/A'])[0] if chart_data.get('top_names') else 'N/A'
    top_item_value = chart_data.get('top_values', [0])[0] if chart_data.get('top_values') else 0
    lowest_item_name = chart_data.get('top_names', ['N/A'])[-1] if chart_data.get('top_names') else 'N/A'
    lowest_item_value = chart_data.get('top_values', [0])[-1] if chart_data.get('top_values') else 0
    forecast_total = sum(chart_data.get('forecast_values', [0]))

    # Smart revenue formatting
    def format_revenue(value):
        value = float(value)
        if value >= 1_000_000_000:
            return f"₦{value / 1_000_000_000:.2f}B"
        elif value >= 1_000_000:
            return f"₦{value / 1_000_000:.2f}M"
        else:
            return f"₦{int(value):,}"

    total_formatted = format_revenue(summary.get('total_revenue', 0))
    avg_formatted = format_revenue(summary.get('avg_daily', 0))

    context = {
        'analysis': analysis,
        'summary': summary,
        'chart_data': chart_data,
        'busiest_percentage': busiest_percentage,
        'top_item_name': top_item_name,
        'top_item_value': top_item_value,
        'lowest_item_name': lowest_item_name,
        'lowest_item_value': lowest_item_value,
        'forecast_total': forecast_total,
        'total_formatted': total_formatted,
        'avg_formatted': avg_formatted,
    }
    return render(request, 'analysis_detail.html', context)
@login_required
def direct_upload(request):
    if request.method == 'POST':
        file = request.FILES['file']
        business_type = request.POST['business_type']
        
        # Read file
        try:
            if file.name.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
        except Exception as e:
            messages.error(request, f"Could not read file: {str(e)}")
            return redirect('dashboard')
        
        # Basic cleaning
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date'])
        
        revenue_col = "Total Amount" if "Total Amount" in df.columns else "Price"
        if revenue_col not in df.columns:
            messages.error(request, "Revenue column (Total Amount or Price) not found! Try Custom Mapping.")
            return redirect('dashboard')
       
        daily = df.groupby('Date')[revenue_col].sum().reset_index()
       
        total_revenue = float(df[revenue_col].sum())
        total_transactions = int(len(df))
        avg_daily = float(daily[revenue_col].mean())
        growth = float(daily[revenue_col].pct_change().mean() * 100) if len(daily) > 1 else 0.0
       
        # Top items
        if business_type.startswith("Product"):
            top_col = "Product Name"
        else:
            top_col = "Service Name" if "Service Name" in df.columns else df.columns[1]
        top = df.groupby(top_col)[revenue_col].sum().nlargest(5)
        top_names = top.index.astype(str).tolist()
        top_values = [float(x) for x in top.values.tolist()]
       
        # Busy days
        df['Day'] = df['Date'].dt.day_name()
        busy = df.groupby('Day')[revenue_col].sum().reindex([
            'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'
        ])
        busy_days = busy.index.tolist()
        busy_values = [float(x) if pd.notna(x) else 0 for x in busy.values.tolist()]
       
        # Forecast (next 7 days)
        daily_sorted = daily.sort_values('Date')
        X = np.arange(len(daily_sorted)).reshape(-1, 1)
        y = daily_sorted[revenue_col].values
        model = LinearRegression().fit(X, y)
        future_X = np.arange(len(daily_sorted), len(daily_sorted) + 7).reshape(-1, 1)
        pred = model.predict(future_X)
       
        last_date = daily_sorted['Date'].iloc[-1]
        forecast_dates = [(last_date + timedelta(days=i+1)).strftime('%Y-%m-%d') for i in range(7)]
        forecast_values = [float(x) for x in pred.tolist()]
       
        # Historical dates/revenue for forecast chart
        historical_dates = daily_sorted['Date'].astype(str).tolist()
        historical_revenue = [float(x) for x in daily_sorted[revenue_col].tolist()]
       
        # Daily trend
        daily_dates = daily['Date'].astype(str).tolist()
        daily_revenue = [float(x) for x in daily[revenue_col].tolist()]
       
        # Anonymized hash
        data_hash = hashlib.sha256(pd.util.hash_pandas_object(df).values).hexdigest()
       
        # Full summary with chart data
        summary = {
            'total_revenue': total_revenue,
            'transactions': total_transactions,
            'avg_daily': avg_daily,
            'growth': growth,
            'chart_data': {
                'daily_dates': daily_dates,
                'daily_revenue': daily_revenue,
                'top_names': top_names,
                'top_values': top_values,
                'busy_days': busy_days,
                'busy_values': busy_values,
                'historical_dates': historical_dates,
                'historical_revenue': historical_revenue,
                'forecast_dates': forecast_dates,
                'forecast_values': forecast_values,
            }
        }
        title = request.POST.get('title', 'Untitled Analysis')
       
        Analysis.objects.create(
            user=request.user,
            business_type=business_type,
            data_summary=summary,
            raw_data_hash=data_hash,
            uploaded_file=file,
            title=title
        )
       
        messages.success(request, 'Direct analysis completed and saved successfully!')
        return redirect('dashboard')
    
    return redirect('dashboard')


@login_required
def download_analysis_pdf(request, pk):
    analysis = Analysis.objects.get(pk=pk, user=request.user)
    summary = analysis.data_summary
    chart_data = summary.get('chart_data', {})

    # Create PDF
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, height - 80, f"AI Business Insights Report")
    p.setFont("Helvetica", 12)
    p.drawString(50, height - 110, f"Title: {analysis.title or 'Untitled'}")
    p.drawString(50, height - 130, f"Business Type: {analysis.business_type}")
    p.drawString(50, height - 150, f"Date: {analysis.created_at.date()}")

    # KPIs
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, height - 190, "Key Metrics:")
    p.setFont("Helvetica", 11)
    p.drawString(70, height - 210, f"Total Revenue: ₦{summary.get('total_revenue', 0):,.0f}")
    p.drawString(70, height - 230, f"Total Transactions: {summary.get('transactions', 0)}")
    p.drawString(70, height - 250, f"Avg Daily Revenue: ₦{summary.get('avg_daily', 0):,.0f}")
    p.drawString(70, height - 270, f"Growth: {summary.get('growth', 0):+.1f}%")

    # Top Items
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, height - 310, "Top 5 Products/Services:")
    p.setFont("Helvetica", 11)
    top_names = chart_data.get('top_names', [])
    top_values = chart_data.get('top_values', [])
    for i in range(min(5, len(top_names))):
        p.drawString(70, height - 330 - i*20, f"{i+1}. {top_names[i]} - ₦{top_values[i]:,.0f}")

    # Busy Days
    p.setFont("Helvetica-Bold", 12)
    p.drawString(300, height - 190, "Busy Days:")
    p.setFont("Helvetica", 11)
    busy_days = chart_data.get('busy_days', [])
    busy_values = chart_data.get('busy_values', [])
    for i in range(len(busy_days)):
        p.drawString(320, height - 210 - i*20, f"{busy_days[i]}: ₦{busy_values[i]:,.0f}")

    # Forecast
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, height - 450, "7-Day Forecast:")
    p.setFont("Helvetica", 11)
    forecast_dates = chart_data.get('forecast_dates', [])
    forecast_values = chart_data.get('forecast_values', [])
    for i in range(len(forecast_dates)):
        p.drawString(70, height - 470 - i*20, f"{forecast_dates[i]}: ₦{forecast_values[i]:,.0f}")

    p.showPage()
    p.save()
    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{analysis.title or "report"}_{analysis.created_at.date()}.pdf"'
    response.write(pdf)
    return response

@login_required
def delete_analysis(request, pk):
    analysis = Analysis.objects.get(pk=pk, user=request.user)
    analysis.delete()
    messages.success(request, "Analysis deleted")
    return redirect('dashboard')
