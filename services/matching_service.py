"""Job matching service — filters jobs by subscriber preferences."""
from datetime import datetime, timezone, timedelta
from sqlalchemy import or_

from models.job import Job
from models.subscriber import Subscriber
from utils.logger import get_logger

logger = get_logger('matching')

MIN_MATCH_SCORE = 0.25


def find_matching_jobs(subscriber, jobs=None):
    """
    Find jobs that match a subscriber's preferences.
    Optimized to pre-filter at the SQL level where possible.
    """
    if jobs is None:
        since = datetime.now(timezone.utc) - timedelta(hours=24)

        # Build a base query that pre-filters at the DB level
        query = Job.query.filter(Job.scraped_at >= since)

        # If subscriber has location or job_type preferences, push those to SQL
        if subscriber.location:
            locs = [l.strip().lower() for l in subscriber.location.split(',') if l.strip()]
            if locs and 'remote' not in locs:
                loc_filters = []
                for loc in locs:
                    loc_filters.append(Job.location.ilike(f'%{loc}%'))
                query = query.filter(or_(*loc_filters))

        if subscriber.job_type and subscriber.job_type.lower() != 'any':
            query = query.filter(Job.job_type.ilike(f'%{subscriber.job_type}%'))

        # If subscriber has skills, try to pre-filter jobs that have skills listed
        if subscriber.skills:
            skills_list = [s.strip().lower() for s in subscriber.skills.split(',') if s.strip()]
            if skills_list:
                skill_filters = []
                for skill in skills_list:
                    skill_filters.append(Job.skills.ilike(f'%{skill}%'))
                query = query.filter(or_(*skill_filters))

        jobs = query.all()

    if not jobs:
        return []

    # Check if subscriber has any preferences at all
    has_prefs = bool(subscriber.skills or subscriber.role or
                     subscriber.location or
                     (subscriber.job_type and subscriber.job_type.lower() != 'any'))

    if not has_prefs:
        logger.info(f'Subscriber {subscriber.email} has no preferences, sending latest jobs')
        return sorted(jobs, key=lambda j: j.scraped_at or '', reverse=True)[:20]

    matching = []
    for job in jobs:
        score = calculate_match_score(subscriber, job)
        if score >= MIN_MATCH_SCORE:
            matching.append((job, score))

    matching.sort(key=lambda x: x[1], reverse=True)
    result = [job for job, score in matching]

    logger.info(f'Subscriber {subscriber.email}: {len(result)}/{len(jobs)} jobs matched '
                f'(skills={subscriber.skills!r}, role={subscriber.role!r}, '
                f'loc={subscriber.location!r}, type={subscriber.job_type!r})')
    return result


def calculate_match_score(subscriber, job):
    """
    Calculate how well a job matches subscriber preferences.
    Returns 0.0 (no match) to 1.0 (perfect match).
    """
    score = 0.0
    max_possible = 0.0

    # ── Skills match (weight: 4) ──
    if subscriber.skills:
        max_possible += 4
        job_skills = job.skills or ''
        sub_skills = [s.strip().lower() for s in subscriber.skills.split(',') if s.strip()]
        job_skills_list = [s.strip().lower() for s in job_skills.split(',') if s.strip()]

        if not job_skills_list:
            score += 0.5
        else:
            overlap = len(set(sub_skills) & set(job_skills_list))
            if overlap == 0:
                return 0.0
            score += 4 * (overlap / len(sub_skills))

    # ── Role match (weight: 3) ──
    if subscriber.role:
        max_possible += 3
        role_lower = subscriber.role.lower().strip()
        title_lower = job.title.lower()

        if role_lower in title_lower:
            score += 3
        else:
            role_words = [w for w in role_lower.split() if len(w) > 2]
            matching_words = [rw for rw in role_words if rw in title_lower]
            if matching_words:
                score += 3 * (len(matching_words) / len(role_words))
            else:
                title_words = set(title_lower.split())
                role_aliases = {
                    'developer': {'dev', 'development', 'engineer', 'coding', 'programmer', 'sde'},
                    'engineer': {'developer', 'dev', 'engineering', 'sde', 'programming'},
                    'frontend': {'front-end', 'front end', 'ui', 'react', 'angular', 'vue', 'css', 'html'},
                    'backend': {'back-end', 'back end', 'api', 'server', 'django', 'flask', 'node'},
                    'full stack': {'fullstack', 'full-stack', 'mern', 'mean'},
                    'data scientist': {'data science', 'ml', 'machine learning', 'analytics'},
                    'devops': {'dev ops', 'sre', 'infrastructure', 'ci/cd', 'cloud'},
                }
                alias_match = False
                for keyword, aliases in role_aliases.items():
                    if keyword in role_lower:
                        if any(alias in title_lower for alias in aliases):
                            score += 1.5
                            alias_match = True
                            break
                if not alias_match:
                    return 0.0

    # ── Location match (weight: 2) ──
    if subscriber.location:
        max_possible += 2
        sub_locs = [l.strip().lower() for l in subscriber.location.split(',') if l.strip()]
        job_loc = (job.location or '').lower()

        if 'remote' in sub_locs or 'remote' in job_loc:
            score += 2
        elif any(loc in job_loc for loc in sub_locs):
            score += 2
        else:
            city_aliases = {
                'bangalore': 'bengaluru', 'bengaluru': 'bangalore',
                'mumbai': 'bombay', 'bombay': 'mumbai',
                'chennai': 'madras', 'madras': 'chennai',
                'kolkata': 'calcutta', 'calcutta': 'kolkata',
                'delhi': 'new delhi', 'new delhi': 'delhi',
                'noida': 'noida', 'gurgaon': 'gurugram', 'gurugram': 'gurgaon',
                'hyderabad': 'hyderabad', 'pune': 'pune',
            }
            loc_match = False
            for sub_loc in sub_locs:
                alias = city_aliases.get(sub_loc, '')
                if alias and alias in job_loc:
                    score += 2
                    loc_match = True
                    break
                if sub_loc and sub_loc in job_loc:
                    score += 2
                    loc_match = True
                    break
            if not loc_match:
                return 0.0

    # ── Job type match (weight: 1) ──
    if subscriber.job_type and subscriber.job_type.lower() != 'any':
        max_possible += 1
        if subscriber.job_type.lower() in (job.job_type or '').lower():
            score += 1
        else:
            return 0.0

    if max_possible == 0:
        return 0.0
    return score / max_possible
