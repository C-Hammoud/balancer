from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, get_user_model, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from firebase_admin import auth as fb_auth, firestore
from firebase_client import get_firestore_client, get_storage_bucket

from expenses.store import ConsumptionFS as Consumption
from .forms import ExpenseDateForm, ExpenseLineItemForm, ConsumptionEditForm, UserRegisterForm, UserUpdateForm
from .models import TZ_TO_COUNTRY, Currency, COUNTRIES

from datetime import datetime, date
from calendar import month_name
from decimal import Decimal
import json
import io
import uuid

# PDF + chart generation
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors

import matplotlib
matplotlib.use("Agg")   # for headless servers
import matplotlib.pyplot as plt
from django.conf import settings
from django.forms import formset_factory


def _trigger_budget_alerts(user, when_date=None):
    """Re-evaluate budget alerts after expense mutations."""
    try:
        from budgeting.alerts import evaluate_budget_alerts
        y = when_date.year if when_date else None
        m = when_date.month if when_date else None
        evaluate_budget_alerts(user, year=y, month=m)
    except Exception:
        pass


def register(request):
    if request.method == "POST":
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_user = authenticate(
                request,
                username=form.cleaned_data.get("username"),
                password=form.cleaned_data.get("password1"),
            )
            if auth_user is not None:
                login(request, auth_user)
            else:
                user.backend = "django.contrib.auth.backends.ModelBackend"
                login(request, user)
            messages.success(request, "Account created! You’re now logged in.")
            return redirect("dashboard")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = UserRegisterForm()
    return render(request, "registration/register.html", {"form": form})

def health_check(request):
    return JsonResponse({"status": "ok"})

def _sync_firebase_profile(user, password: str | None = None):
    uid = user.username
    if not uid:
        return
    email = user.email or ""
    name = (user.get_full_name() or "").strip()
    try:
        fb_auth.update_user(
            uid,
            email=email or None,
            display_name=name or None,
            password=password or None,
        )
    except Exception as e:
        print(f"Firebase auth update error: {e}")
    try:
        db = get_firestore_client()
        if db:
            user_ref = db.collection("users").document(uid)
            user_ref.set({
                "uid": uid,
                "email": email,
                "name": name,
            }, merge=True)
    except Exception as e:
        print(f"Firestore profile update error: {e}")

@login_required
def user_settings(request):
    profile_form = UserUpdateForm(instance=request.user)
    password_form = PasswordChangeForm(request.user)

    if request.method == "POST":
        if "save_profile" in request.POST:
            profile_form = UserUpdateForm(request.POST, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                _sync_firebase_profile(request.user)
                messages.success(request, "Profile updated successfully.")
                return redirect("user_settings")
            messages.error(request, "Please correct the profile errors.")
        elif "save_password" in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                _sync_firebase_profile(user, password_form.cleaned_data.get("new_password1"))
                messages.success(request, "Password updated successfully.")
                return redirect("user_settings")
            messages.error(request, "Please correct the password errors.")

    return render(request, "expenses/user_settings.html", {
        "profile_form": profile_form,
        "password_form": password_form,
    })

def upload_to_firebase(file_obj, filename):
    bucket = get_storage_bucket()
    if bucket is None:
        raise RuntimeError("Firebase storage bucket not initialized.")
    blob = bucket.blob(filename)
    blob.upload_from_file(file_obj)
    blob.make_public()
    return blob.public_url

# @login_required
# def add_expense(request):
#     if request.method == "POST":
#         form = ConsumptionCreateForm(request.POST)
#         if form.is_valid():
#             expense = form.save(created_by=request.user)
#             messages.success(request, "Expense added successfully.")
#             return redirect("dashboard")
#         else:
#             messages.error(request, "Could not add expense: " + str(form.errors))
#     else:
#         form = ConsumptionCreateForm()
#     return render(request, "expenses/add_expense.html", {"form": form})
@login_required
def add_expense(request):
    
    print(f"Request GET params: {request.GET.dict()}") 
    country_choices = sorted(list(COUNTRIES.choices), key=lambda x: x[1])

    default_country = ""
    client_tz = request.GET.get("tz")
    server_tz = getattr(settings, "TIME_ZONE", "") or ""

    if client_tz in TZ_TO_COUNTRY:
        default_country = TZ_TO_COUNTRY[client_tz]
        print(f"Detected timezone from client: {client_tz}, setting default country to {default_country}")
    elif server_tz in TZ_TO_COUNTRY:
        default_country = TZ_TO_COUNTRY[server_tz]
        print(f"Detected server timezone: {server_tz}, setting default country to {default_country}")   
    else:
        default_country = COUNTRIES.LB  # fallback
    
    LineItemFormSet = formset_factory(ExpenseLineItemForm, extra=1)

    if request.method == "POST":
        date_form = ExpenseDateForm(request.POST)
        items_formset = LineItemFormSet(request.POST, prefix="items")
        if date_form.is_valid() and items_formset.is_valid():
            created_count = 0
            expense_date = date_form.cleaned_data["date"]
            selected_country = request.POST.get("country") or default_country
            for item_form in items_formset:
                if not item_form.cleaned_data:
                    continue
                amount = item_form.cleaned_data.get("amount")
                if amount is None:
                    continue
                c = Consumption(
                    pk=str(uuid.uuid4()),
                    date=expense_date,
                    amount=Decimal(str(amount)),
                    currency=item_form.cleaned_data.get("currency"),
                    consumption_type=item_form.cleaned_data.get("consumption_type"),
                    note=item_form.cleaned_data.get("note", ""),
                    country=selected_country,
                    created_by=str(request.user.id) if request.user else None,
                    created_at=datetime.utcnow(),
                    modified_by=None,
                    modified_at=None,
                    record_status="active"
                )
                c.save()  # Triggers compute_amount_usd and saves to Firestore
                created_count += 1
            if created_count == 0:
                messages.error(request, "Please add at least one expense.")
            else:
                messages.success(request, f"{created_count} expense(s) added successfully.")
                _trigger_budget_alerts(request.user, expense_date)
                return redirect("dashboard")
        else:
            messages.error(request, f"Could not add expense: {date_form.errors} {items_formset.errors}")
    else:
        date_form = ExpenseDateForm(initial={"date": date.today()})
        items_formset = LineItemFormSet(prefix="items")

    return render(request, "expenses/add_expense.html", {
        "date_form": date_form,
        "items": items_formset,
        "country_choices": country_choices,
        "default_country": default_country,
    })
    
    
@login_required
def dashboard(request):
    months = [(i, month_name[i]) for i in range(1, 13)]
    current_year = 2025
    print(f"Current year: {current_year}")
    start_year = 2025
    years = [(y) for y in range(start_year, current_year + 2)]
    selected_month = int(request.GET.get("month", datetime.now().month))
    selected_year = int(request.GET.get("year", datetime.now().year))
    selected_month_name = month_name[selected_month]
    show_monthly_only = request.GET.get("show_monthly") == "1"

    try:
        all_items = Consumption.list(limit=2000)
    except Exception as e:
        print(f"Error fetching Firestore data: {e}")
        all_items = []

    yearly_items = [
        i for i in all_items
        if i.record_status == "active"
        and i.created_by == str(request.user.id)
        and getattr(i, "date", None) is not None
        and i.date.year == selected_year
    ]
    month_totals = {m: 0.0 for m, _ in months}
    month_counts = {m: 0 for m, _ in months}
    for item in yearly_items:
        month_num = item.date.month
        month_totals[month_num] += float(item.amount_usd)
        month_counts[month_num] += 1
    yearly_overview = [
        (m, name, month_totals[m], month_counts[m]) for m, name in months
    ]
    yearly_labels = [name for _, name in months]
    yearly_values = [month_totals[m] for m, _ in months]

    monthly = [
        i for i in all_items
        if i.record_status == "active"
        and i.created_by == str(request.user.id)
        and getattr(i, "date", None) is not None
        and i.date.year == selected_year
        and i.date.month == selected_month
    ]

    total_usd = sum([float(i.amount_usd) for i in monthly]) if monthly else 0.0
    total_count = len(monthly)
    yearly_total_usd = sum([float(i.amount_usd) for i in yearly_items]) if yearly_items else 0.0
    yearly_total_count = len(yearly_items)
    yearly_average = (yearly_total_usd / yearly_total_count) if yearly_total_count else 0.0

    totals = {}
    for i in monthly:
        key = (i.consumption_type or "other").capitalize()
        totals[key] = totals.get(key, 0.0) + float(i.amount_usd)

    labels = list(totals.keys())
    values = [totals[k] for k in labels]
    breakdown = []
    for label, value in zip(labels, values):
        percent = round((value / total_usd) * 100, 2) if total_usd > 0 else 0
        breakdown.append((label, value, percent))

    context = {
        "months": months,
        "years": years,
        "selected_month": selected_month,
        "selected_year": selected_year,
        "selected_month_name": selected_month_name,
        "show_monthly_only": show_monthly_only,
        "yearly_overview": yearly_overview,
        "yearly_labels": json.dumps(yearly_labels),
        "yearly_values": json.dumps(yearly_values),
        "total": yearly_total_usd,
        "total_count": yearly_total_count,
        "average": yearly_average,
        "labels": json.dumps(labels),
        "values": json.dumps(values),
        "breakdown": breakdown,
    }

    # Budget utilization widgets (merged with budgeting app)
    try:
        from budgeting.services import budget_utilization_report
        from budgeting.store import BudgetAlertFS
        from budgeting.alerts import evaluate_budget_alerts
        now = datetime.now()
        budget_year = now.year
        budget_month = now.month
        try:
            evaluate_budget_alerts(request.user, year=budget_year, month=budget_month)
        except Exception:
            pass
        report = budget_utilization_report(request.user, budget_year, budget_month)
        warn_rows = [r for r in report["rows"] if r.get("status") in ("warn", "critical", "over")]
        warn_rows.sort(key=lambda r: r.get("utilization_pct") or 0, reverse=True)
        open_alerts = BudgetAlertFS.list_by_user(str(request.user.pk), open_only=True, limit=10)
        context.update({
            "budget_overall_util": report.get("overall_util"),
            "budget_overall_status": report.get("overall_status"),
            "budget_remaining": report.get("remaining"),
            "budget_total_forecast": report.get("total_forecast"),
            "budget_total_actual": report.get("total_actual"),
            "budget_warn_rows": warn_rows[:5],
            "budget_open_alerts": open_alerts[:5],
            "budget_month_str": f"{budget_year}-{budget_month:02d}",
        })
    except Exception as e:
        print(f"Budget widget error: {e}")
        context.update({
            "budget_overall_util": None,
            "budget_overall_status": None,
            "budget_remaining": None,
            "budget_total_forecast": None,
            "budget_total_actual": None,
            "budget_warn_rows": [],
            "budget_open_alerts": [],
            "budget_month_str": "",
        })

    return render(request, "expenses/dashboard.html", context)

@login_required
def monthly_list(request):
    months = [(i, month_name[i]) for i in range(1, 13)]
    current_year = datetime.now().year
    years = list(range(2025, current_year + 1))

    selected_month = int(request.GET.get("month", datetime.now().month))
    selected_year = int(request.GET.get("year", datetime.now().year))
    selected_month_name = month_name[selected_month]
    page_size_param = (request.GET.get("page_size") or "10").lower()

    try:
        all_items = Consumption.list(limit=2000)
    except Exception as e:
        print(f"Error fetching Firestore data: {e}")
        all_items = []

    qs = [
        i for i in all_items
        if i.record_status == "active"
        and i.created_by == str(request.user.id)
        and getattr(i, "date", None) is not None
        and i.date.year == selected_year
        and i.date.month == selected_month
    ]
    qs.sort(key=lambda x: getattr(x, "date", datetime.min), reverse=True)

    total_usd = sum([float(i.amount_usd) for i in qs]) if qs else Decimal('0.00')

    totals = {}
    for i in qs:
        key = (i.consumption_type or "other").capitalize()
        totals[key] = totals.get(key, 0.0) + float(i.amount_usd)
    labels = list(totals.keys())
    values = [totals[k] for k in labels]
    breakdown = []
    for label, value in zip(labels, values):
        percent = round((value / float(total_usd)) * 100, 2) if total_usd else 0
        breakdown.append((label, value, percent))

    if page_size_param == "all":
        per_page = max(len(qs), 1)
    else:
        try:
            per_page = int(page_size_param)
        except ValueError:
            per_page = 10
        if per_page not in (10, 50):
            per_page = 10

    paginator = Paginator(qs, per_page)
    page_number = request.GET.get("page")
    expenses_page = paginator.get_page(page_number)

    return render(request, "expenses/monthly_list.html", {
        'months': months,
        'years': years,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'selected_month_name': selected_month_name,
        'total_usd': total_usd,
        'expenses': expenses_page,
        'page_size': page_size_param,
        'labels': json.dumps(labels),
        'values': json.dumps(values),
        'breakdown': breakdown,
        'consumption_choices': [(c, c.capitalize()) for c in ['market', 'transport' , 'food', 'other']],
        'currency_choices': Currency.choices,
    })

@login_required
def edit_expense(request, pk):
    inst = Consumption.get(str(pk))
    if not inst or inst.created_by != str(request.user.id):
        messages.error(request, "Expense not found or not owned by you.")
        return redirect("monthly_list")

    if request.method == "POST":
        form = ConsumptionEditForm(request.POST, instance=inst)
        if form.is_valid():
            form.save(modified_by=request.user)
            messages.success(request, "Expense updated successfully.")
            _trigger_budget_alerts(request.user, inst.date)
            month = request.POST.get("month")
            year = request.POST.get("year")
            page = request.POST.get("page")
            page_size = request.POST.get("page_size")
            if month and year:
                query = f"month={month}&year={year}"
                if page_size:
                    query += f"&page_size={page_size}"
                if page:
                    query += f"&page={page}"
                return redirect(f"/list/?{query}")
            return redirect("monthly_list")
        else:
            messages.error(request, "Could not save changes: " + str(form.errors))
    else:
        form = ConsumptionEditForm(instance=inst)
    return render(request, "expenses/edit_expense.html", {"form": form})

@login_required
def delete_expense(request, pk):
    inst = Consumption.get(str(pk))
    if not inst or inst.created_by != str(request.user.id):
        messages.error(request, "Expense not found or not owned by you.")
        return redirect("monthly_list")
    if request.method == "POST":
        inst.record_status = "deleted"
        inst.modified_by = str(request.user.id)
        inst.modified_at = datetime.utcnow()
        inst.save()
        messages.success(request, "Expense deleted successfully.")
        _trigger_budget_alerts(request.user, inst.date)
    return redirect("monthly_list")

@csrf_exempt
def firebase_token_login(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    token = request.POST.get("idToken") or request.headers.get("Authorization")
    if not token:
        return JsonResponse({"error": "missing token"}, status=400)
    if token.startswith("Bearer "):
        token = token.split(" ", 1)[1]

    try:
        decoded = fb_auth.verify_id_token(token)
    except Exception:
        return JsonResponse({"error": "invalid token"}, status=401)

    uid = decoded.get("uid")
    email = decoded.get("email", "")
    name = decoded.get("name") or decoded.get("displayName") or ""
    photo = decoded.get("picture")
    email_verified = decoded.get("email_verified", False)

    try:
        db = get_firestore_client()
        user_ref = db.collection("users").document(uid)
        snapshot = user_ref.get()
        user_payload = {
            "uid": uid,
            "email": email,
            "name": name,
            "photo": photo,
            "email_verified": email_verified,
        }
        if not snapshot.exists:
            user_ref.set({
                **user_payload,
                "created_at": firestore.SERVER_TIMESTAMP,
                "last_login": firestore.SERVER_TIMESTAMP,
            })
        else:
            user_ref.update({
                **user_payload,
                "last_login": firestore.SERVER_TIMESTAMP,
            })
    except Exception as e:
        print(f"Firestore error: {e}")

    User = get_user_model()
    user, created = User.objects.get_or_create(
        username=uid,
        defaults={"email": email, "first_name": name or ""}
    )
    if not created and email and user.email != email:
        user.email = email
        user.save(update_fields=["email"])

    login(request, user)
    return JsonResponse({"ok": True})

@login_required
def download_dashboard_pdf(request):
    """
    Generate a professional PDF report for the dashboard (month + year).
    Includes summary, styled breakdown table, pie chart, and footer.
    """

    selected_month = int(request.GET.get("month", datetime.now().month))
    selected_year = int(request.GET.get("year", datetime.now().year))
    scope = request.GET.get("scope", "month").lower()
    months_param = request.GET.getlist("months")
    selected_months = sorted({
        int(m) for m in months_param
        if str(m).isdigit() and 1 <= int(m) <= 12
    })

    # --- Fetch Data ---
    try:
        all_items = Consumption.list(limit=2000)
    except Exception as e:
        print(f"Error fetching Firestore data: {e}")
        all_items = []

    if scope == "year":
        period_items = [
            i for i in all_items
            if i.record_status == "active"
            and i.created_by == str(request.user.id)
            and getattr(i, "date", None) is not None
            and i.date.year == selected_year
        ]
    elif scope == "months" and selected_months:
        period_items = [
            i for i in all_items
            if i.record_status == "active"
            and i.created_by == str(request.user.id)
            and getattr(i, "date", None) is not None
            and i.date.year == selected_year
            and i.date.month in selected_months
        ]
    else:
        period_items = [
            i for i in all_items
            if i.record_status == "active"
            and i.created_by == str(request.user.id)
            and getattr(i, "date", None) is not None
            and i.date.year == selected_year
            and i.date.month == selected_month
        ]

    total_usd = sum([float(i.amount_usd) for i in period_items]) if period_items else 0.0
    total_count = len(period_items)

    totals = {}
    for i in period_items:
        key = (i.consumption_type or "other").capitalize()
        totals[key] = totals.get(key, 0.0) + float(i.amount_usd)

    # --- Metadata ---
    extracted_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    extractor_name = request.user.get_full_name() or request.user.username

    # --- Pie Chart removed (stacked bars used instead) ---
    pie_image = None

    # --- Monthly Charts (one per country per month) ---
    monthly_charts = []
    if scope == "month":
        months_for_charts = [selected_month]
    else:
        months_for_charts = selected_months if (scope == "months" and selected_months) else list(range(1, 13))

    for m in months_for_charts:
        month_items = [
            i for i in period_items
            if getattr(i, "date", None) is not None and i.date.month == m
        ]
        if not month_items:
            continue
        items_by_country = {}
        for i in month_items:
            country = (getattr(i, "country", "") or "Unknown").upper()
            items_by_country.setdefault(country, []).append(i)
        for country_code, items in items_by_country.items():
            month_totals = {}
            for i in items:
                key = (i.consumption_type or "other").capitalize()
                month_totals[key] = month_totals.get(key, 0.0) + float(i.amount_usd)
            if not month_totals:
                continue
            labels = list(month_totals.keys())
            values = [month_totals[k] for k in labels]
            fig, ax = plt.subplots(figsize=(5.0, 3.6), dpi=100)
            wedges, _ = ax.pie(
                values,
                startangle=90,
                wedgeprops={"width": 0.4}
            )
            ax.legend(
                wedges,
                labels,
                title="Category",
                loc="center left",
                bbox_to_anchor=(1.0, 0.5),
                fontsize=8,
                title_fontsize=8
            )
            ax.set_title(f"{month_name[m]} {selected_year} • {country_code}")
            ax.set_aspect("equal", adjustable="box")
            buf = io.BytesIO()
            plt.tight_layout()
            plt.savefig(buf, format="png", bbox_inches="tight", transparent=True)
            plt.close(fig)
            buf.seek(0)
            monthly_charts.append({
                "image": ImageReader(buf),
                "totals": month_totals,
                "total": sum(month_totals.values()),
            })

    # --- Yearly Chart (stacked bar) ---
    yearly_image = None
    if scope in ("year", "months"):
        if scope == "months" and selected_months:
            months_for_chart = selected_months
        else:
            months_for_chart = list(range(1, 13))
        month_totals = {m: 0.0 for m in months_for_chart}
        for item in period_items:
            month_num = item.date.month
            if month_num in month_totals:
                month_totals[month_num] += float(item.amount_usd)
        month_labels = [month_name[m][:3] for m in months_for_chart]
        month_values = [month_totals[m] for m in months_for_chart]
        category_order = []
        category_totals = {}
        for item in period_items:
            month_num = item.date.month
            if month_num not in month_totals:
                continue
            key = (item.consumption_type or "other").capitalize()
            if key not in category_totals:
                category_totals[key] = {m: 0.0 for m in months_for_chart}
                category_order.append(key)
            category_totals[key][month_num] += float(item.amount_usd)
        if any(month_values):
            fig, ax = plt.subplots(figsize=(7.5, 3.2), dpi=100)
            bottoms = [0.0 for _ in months_for_chart]
            colors_list = ["#36a2eb", "#ff6384", "#ffcd56", "#4bc0c0", "#9966ff", "#ff9f40"]
            for idx, key in enumerate(category_order):
                values = [category_totals[key][m] for m in months_for_chart]
                ax.bar(
                    month_labels,
                    values,
                    bottom=bottoms,
                    color=colors_list[idx % len(colors_list)],
                    label=key
                )
                bottoms = [b + v for b, v in zip(bottoms, values)]
            ax.set_ylabel("USD")
            ax.set_title("Monthly Totals (Stacked)")
            ax.grid(axis="y", linestyle="--", alpha=0.3)
            ax.legend(loc="upper right", fontsize=7, title_fontsize=7)
            buf = io.BytesIO()
            plt.tight_layout()
            plt.savefig(buf, format="png", bbox_inches="tight", transparent=True)
            plt.close(fig)
            buf.seek(0)
            yearly_image = ImageReader(buf)

    # --- PDF Setup ---
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin_x, margin_y = 25 * mm, 20 * mm
    y = height - margin_y

    def draw_footer():
        p.setStrokeColor(colors.lightgrey)
        p.setLineWidth(0.5)
        p.line(margin_x, margin_y + 10, width - margin_x, margin_y + 10)
        p.setFont("Helvetica", 8)
        p.drawString(margin_x, margin_y, f"Generated by: {extractor_name}")
        p.drawRightString(width - margin_x, margin_y, f"Extracted: {extracted_at}")

    def draw_breakdown_table(start_y, breakdown_totals, overall_total, title="Breakdown"):
        y_local = start_y
        if not breakdown_totals or overall_total <= 0:
            return y_local
        p.setFont("Helvetica-Bold", 10)
        p.drawString(margin_x, y_local, title)
        y_local -= 12
        p.setFont("Helvetica-Bold", 9)
        p.drawString(margin_x, y_local, "Type")
        p.drawRightString(width - margin_x - 80, y_local, "Amount")
        p.drawRightString(width - margin_x, y_local, "%")
        y_local -= 10
        p.setStrokeColor(colors.grey)
        p.line(margin_x, y_local, width - margin_x, y_local)
        y_local -= 12
        p.setFont("Helvetica", 9)
        for label, amt in breakdown_totals.items():
            percent = (amt / overall_total) * 100
            p.drawString(margin_x, y_local, label)
            p.drawRightString(width - margin_x - 80, y_local, f"{amt:,.2f}")
            p.drawRightString(width - margin_x, y_local, f"{percent:.1f}%")
            y_local -= 12
            if y_local < margin_y + 50:
                draw_footer()
                p.showPage()
                y_local = height - margin_y
        return y_local

    # --- Header (colored band) ---
    header_h = 22 * mm
    p.setFillColorRGB(0.12, 0.44, 0.71)  # dark blue
    p.rect(0, height - header_h, width, header_h, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 18)
    p.drawString(margin_x, height - header_h + 8, "Finance Tracker")
    p.setFont("Helvetica", 10)
    if scope == "year":
        title = "Yearly Expense Report"
    elif scope == "months" and selected_months:
        title = "Selected Months Report"
    else:
        title = "Monthly Expense Report"
    p.drawRightString(width - margin_x, height - header_h + 12, title)
    p.drawRightString(width - margin_x, height - header_h + 2, extracted_at)    
    # --- Subtitle ---
    y = height - header_h - 15
    p.setFillColor(colors.black)
    p.setFont("Helvetica-Bold", 13)
    if scope == "year":
        subtitle = f"{selected_year}"
    elif scope == "months" and selected_months:
        month_labels = ", ".join([month_name[m][:3] for m in selected_months])
        subtitle = f"{month_labels} {selected_year}"
    else:
        subtitle = f"{month_name[selected_month]} {selected_year}"
    p.drawString(margin_x, y, subtitle)
    y -= 20

    # --- Summary box ---
    p.setFillColor(colors.whitesmoke)
    p.roundRect(margin_x, y - 30, width - 2 * margin_x, 30, 6, fill=1, stroke=1)
    p.setFillColor(colors.black)
    p.setFont("Helvetica-Bold", 11)
    p.drawString(margin_x + 10, y - 12, f"Total Expenses: {total_usd:,.2f} USD")
    p.setFont("Helvetica", 10)
    p.drawString(margin_x + 10, y - 24, f"Number of Records: {total_count}")
    y -= 50

    if yearly_image:
        chart_w, chart_h = 170 * mm, 70 * mm
        chart_x = (width - chart_w) / 2
        chart_y = y - chart_h
        p.drawImage(yearly_image, chart_x, chart_y, chart_w, chart_h, mask="auto")
        y = chart_y - 16
        y = draw_breakdown_table(y, totals, total_usd, title="Yearly Breakdown")
        y -= 10

    # --- Selected Months Charts ---
    if monthly_charts:
        gap = 8 * mm
        chart_w = (width - 2 * margin_x - gap) / 2
        chart_h = 70 * mm
        col = 0
        for chart_meta in monthly_charts:
            if col == 0:
                chart_y = y - chart_h
                if chart_y < margin_y + 40:
                    draw_footer()
                    p.showPage()
                    y = height - margin_y
                    chart_y = y - chart_h
            chart_x = margin_x + col * (chart_w + gap)
            p.drawImage(chart_meta["image"], chart_x, chart_y, chart_w, chart_h, mask="auto")
            if col == 1:
                y = chart_y - 10
                y = draw_breakdown_table(y, chart_meta["totals"], chart_meta["total"], title="Breakdown")
                y -= 10
            col = (col + 1) % 2
        if col == 1:
            y = chart_y - 10
            y = draw_breakdown_table(y, chart_meta["totals"], chart_meta["total"], title="Breakdown")
            y -= 10

    # --- Pie chart removed ---

    # Overall breakdown removed; rendered per chart

    # --- Footer ---
    draw_footer()

    # Save
    p.save()
    buffer.seek(0)

    if scope == "year":
        filename = f"Finance_Dashboard_Year_{selected_year}.pdf"
    elif scope == "months" and selected_months:
        month_labels = "-".join([month_name[m][:3] for m in selected_months])
        filename = f"Finance_Dashboard_Selected_{month_labels}_{selected_year}.pdf"
    else:
        filename = f"Finance_Dashboard_{month_name[selected_month]}_{selected_year}.pdf"
    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename=\"{filename}\"'
    return response
