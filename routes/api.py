"""API routes for AJAX calls — uses shared stats service to avoid duplication."""
from flask import Blueprint, jsonify
from services.stats_service import (
    get_dashboard_stats,
    get_subscriber_growth_data,
    get_email_chart_data,
    get_source_distribution,
)

api_bp = Blueprint('api', __name__)


@api_bp.route('/stats')
def stats():
    """Get dashboard stats (JSON)."""
    return jsonify(get_dashboard_stats())


@api_bp.route('/chart/subscribers')
def chart_subscribers():
    """Get subscriber growth chart data (JSON)."""
    return jsonify(get_subscriber_growth_data(days=14))


@api_bp.route('/chart/emails')
def chart_emails():
    """Get email stats chart data (JSON)."""
    return jsonify(get_email_chart_data(days=14))


@api_bp.route('/chart/sources')
def chart_sources():
    """Get job source distribution data (JSON)."""
    return jsonify(get_source_distribution(limit=10))
