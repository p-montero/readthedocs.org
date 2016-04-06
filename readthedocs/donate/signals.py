from django.dispatch import receiver
from django.conf import settings
from django.core.cache import cache

from readthedocs.restapi.signals import footer_response
from readthedocs.donate.models import SupporterPromo, VIEWS, CLICKS, OFFERS, INCLUDE, EXCLUDE


PROMO_GEO_PATH = getattr(settings, 'PROMO_GEO_PATH', None)

if PROMO_GEO_PATH:
    import geoip2.database
    geo_reader = geoip2.database.Reader(PROMO_GEO_PATH)


def show_to_geo(promo, country_code):
    # Remove promo's that exclude this country.
    for filter in promo.geo_filters.all():
        if filter.filter_type == INCLUDE:
            if country_code in filter.codes:
                continue
            else:
                return False
        if filter.filter_type == EXCLUDE:
            if country_code in filter.codes:
                return False

    return True


@receiver(footer_response)
def attach_promo_data(sender, **kwargs):
    request = kwargs['request']
    context = kwargs['context']
    resp_data = kwargs['resp_data']

    project = context['project']

    # Bail out early if promo's are disabled.
    use_promo = getattr(settings, 'USE_PROMOS', True)
    if not use_promo:
        resp_data['promo'] = False
        return

    gold_user = gold_project = False
    promo_obj = None

    show_promo = project.allow_promos

    # The request is by a GoldUser
    if request.user.is_authenticated():
        if request.user.gold.count() or request.user.goldonce.count():
            gold_user = True

    # A GoldUser has mapped this project
    if project.gold_owners.count():
        gold_project = True

    # Don't show gold users promos.
    # This will get overridden if we have specific promos for them below.
    if gold_user or gold_project:
        show_promo = False

    country_code = None

    if PROMO_GEO_PATH:
        # Get geo information from the IP, but don't record it anywhere
        ip = request.META.get('REMOTE_ADDR')
        if ip:
            geo_response = geo_reader.city(ip)
            country_code = geo_response.iso_code

    # Try to get a promo if we should be using one.
    if show_promo:
        promo_queryset = SupporterPromo.objects.filter(live=True, display_type='doc').order_by('?')

        for obj in promo_queryset:
            if country_code:
                if show_to_geo(obj, country_code):
                    promo_obj = obj
        else:
            # TODO: House Ad
            promo_obj = None

        # Support showing a "Thank you" message for gold folks
        if gold_user:
            gold_promo = SupporterPromo.objects.filter(live=True,
                                                       name='gold-user')
            if gold_promo.exists():
                promo_obj = gold_promo.first()

        # Default to showing project-level thanks if it exists
        if gold_project:
            gold_promo = SupporterPromo.objects.filter(live=True,
                                                       name='gold-project')
            if gold_promo.exists():
                promo_obj = gold_promo.first()

    # If we don't have anything to show, don't show it.
    if not promo_obj:
        show_promo = False

    if show_promo:
        promo_dict = promo_obj.as_dict()
        resp_data['promo_data'] = promo_dict
        promo_obj.incr(OFFERS)
        promo_obj.incr(OFFERS, project=project)
        # Set validation cache
        for type in [VIEWS, CLICKS]:
            cache.set(
                promo_obj.cache_key(type=type, hash=promo_dict['hash']),
                0,  # Number of times used. Make this an int so we can detect multiple uses
                60 * 60  # hour
            )
            # Set project for hash key, so we can count it later.
            cache.set(
                promo_obj.cache_key(type='project', hash=promo_dict['hash']),
                project.slug,
                60 * 60  # hour
            )

    # Set promo object on return JSON
    resp_data['promo'] = show_promo
