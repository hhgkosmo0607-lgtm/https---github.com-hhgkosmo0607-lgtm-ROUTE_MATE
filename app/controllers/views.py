from functools import wraps

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user

views_bp = Blueprint("views", __name__)


def login_required_page(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("views.login_page", next=request.path))
        return fn(*args, **kwargs)

    return wrapper


@views_bp.get("/")
def landing():
    return render_template("landing.html")


@views_bp.get("/login")
def login_page():
    return render_template("login.html", next=request.args.get("next", ""))


@views_bp.get("/signup")
def signup_page():
    return render_template("signup.html")


@views_bp.get("/trips")
@login_required_page
def trips_page():
    return render_template("trips.html")


@views_bp.get("/trips/new")
@login_required_page
def trip_new():
    return render_template("trip_new.html")


@views_bp.get("/trips/<int:trip_id>/plan")
@login_required_page
def trip_plan(trip_id):
    return render_template("trip_plan.html", trip_id=trip_id)


@views_bp.get("/trips/<int:trip_id>/map")
@login_required_page
def trip_map(trip_id):
    return render_template("trip_map.html", trip_id=trip_id)


@views_bp.get("/trips/<int:trip_id>/recommend")
@login_required_page
def trip_recommend(trip_id):
    return render_template("trip_recommend.html", trip_id=trip_id)


@views_bp.get("/trips/<int:trip_id>/planb")
@login_required_page
def trip_planb(trip_id):
    return render_template("trip_planb.html", trip_id=trip_id)


@views_bp.get("/trips/<int:trip_id>/checklist")
@login_required_page
def trip_checklist(trip_id):
    return render_template("trip_checklist.html", trip_id=trip_id)


@views_bp.get("/trips/<int:trip_id>/budget")
@login_required_page
def trip_budget(trip_id):
    return render_template("trip_budget.html", trip_id=trip_id)


@views_bp.get("/mypage")
@login_required_page
def mypage():
    return render_template("mypage.html")


@views_bp.get("/shared/<string:token>")
def shared_trip(token):
    return render_template("shared.html", token=token)
