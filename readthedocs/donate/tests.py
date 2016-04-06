import json

from django.test import TestCase
from django.core.urlresolvers import reverse
from django.core.cache import cache

from django_dynamic_fixture import get, fixture

from .models import (SupporterPromo, GeoFilter, Country,
                     CLICKS, VIEWS, OFFERS,
                     INCLUDE, EXCLUDE)
from .signals import show_to_geo
from readthedocs.projects.models import Project


class PromoTests(TestCase):

    def setUp(self):
        self.promo = get(SupporterPromo,
                         slug='promo-slug',
                         link='http://example.com',
                         image='http://media.example.com/img.png')
        self.pip = get(Project, slug='pip', allow_promos=True)

    def test_clicks(self):
        cache.set(self.promo.cache_key(type=CLICKS, hash='random_hash'), 0)
        resp = self.client.get(
            'http://testserver/sustainability/click/%s/random_hash/' % self.promo.id)
        self.assertEqual(resp._headers['location'][1], 'http://example.com')
        promo = SupporterPromo.objects.get(pk=self.promo.pk)
        impression = promo.impressions.first()
        self.assertEqual(impression.clicks, 1)

    def test_views(self):
        cache.set(self.promo.cache_key(type=VIEWS, hash='random_hash'), 0)
        resp = self.client.get(
            'http://testserver/sustainability/view/%s/random_hash/' % self.promo.id)
        self.assertEqual(resp._headers['location'][1], 'http://media.example.com/img.png')
        promo = SupporterPromo.objects.get(pk=self.promo.pk)
        impression = promo.impressions.first()
        self.assertEqual(impression.views, 1)

    def test_project_clicks(self):
        cache.set(self.promo.cache_key(type=CLICKS, hash='random_hash'), 0)
        cache.set(self.promo.cache_key(type='project', hash='random_hash'), self.pip.slug)
        self.client.get('http://testserver/sustainability/click/%s/random_hash/' % self.promo.id)
        promo = SupporterPromo.objects.get(pk=self.promo.pk)
        impression = promo.project_impressions.first()
        self.assertEqual(impression.clicks, 1)

    def test_stats(self):
        for x in range(50):
            self.promo.incr(OFFERS)
        for x in range(20):
            self.promo.incr(VIEWS)
        for x in range(3):
            self.promo.incr(CLICKS)
        self.assertEqual(self.promo.view_ratio(), 0.4)
        self.assertEqual(self.promo.click_ratio(), 0.15)

    def test_multiple_hash_usage(self):
        cache.set(self.promo.cache_key(type=VIEWS, hash='random_hash'), 0)
        self.client.get('http://testserver/sustainability/view/%s/random_hash/' % self.promo.id)
        promo = SupporterPromo.objects.get(pk=self.promo.pk)
        impression = promo.impressions.first()
        self.assertEqual(impression.views, 1)

        # Don't increment again.
        self.client.get('http://testserver/sustainability/view/%s/random_hash/' % self.promo.id)
        promo = SupporterPromo.objects.get(pk=self.promo.pk)
        impression = promo.impressions.first()
        self.assertEqual(impression.views, 1)

    def test_invalid_id(self):
        resp = self.client.get('http://testserver/sustainability/view/invalid/data/')
        self.assertEqual(resp.status_code, 404)

    def test_invalid_hash(self):
        cache.set(self.promo.cache_key(type=VIEWS, hash='valid_hash'), 0)
        resp = self.client.get(
            'http://testserver/sustainability/view/%s/invalid_hash/' % self.promo.id)
        promo = SupporterPromo.objects.get(pk=self.promo.pk)
        self.assertEqual(promo.impressions.count(), 0)
        self.assertEqual(resp._headers['location'][1], 'http://media.example.com/img.png')


class FooterTests(TestCase):

    def setUp(self):
        self.promo = get(SupporterPromo,
                         live=True,
                         slug='promo-slug',
                         display_type='doc',
                         link='http://example.com',
                         image='http://media.example.com/img.png')
        self.pip = get(Project, slug='pip', allow_promos=True)

    def test_footer(self):
        r = self.client.get(
            '/api/v2/footer_html/?project=pip&version=latest&page=index'
        )
        resp = json.loads(r.content)
        self.assertEqual(
            resp['promo_data']['link'],
            '//readthedocs.org/sustainability/click/%s/%s/' % (
                self.promo.pk, resp['promo_data']['hash']
            )
        )
        impression = self.promo.impressions.first()
        self.assertEqual(impression.offers, 1)

    def test_integration(self):
        # Get footer promo
        r = self.client.get(
            '/api/v2/footer_html/?project=pip&version=latest&page=index'
        )
        resp = json.loads(r.content)
        self.assertEqual(
            resp['promo_data']['link'],
            '//readthedocs.org/sustainability/click/%s/%s/' % (
                self.promo.pk, resp['promo_data']['hash'])
        )
        impression = self.promo.impressions.first()
        self.assertEqual(impression.offers, 1)
        self.assertEqual(impression.views, 0)
        self.assertEqual(impression.clicks, 0)

        # Assert view

        r = self.client.get(
            reverse(
                'donate_view_proxy',
                kwargs={'promo_id': self.promo.pk, 'hash': resp['promo_data']['hash']}
            )
        )
        impression = self.promo.impressions.first()
        self.assertEqual(impression.offers, 1)
        self.assertEqual(impression.views, 1)
        self.assertEqual(impression.clicks, 0)

        # Click

        r = self.client.get(
            reverse(
                'donate_click_proxy',
                kwargs={'promo_id': self.promo.pk, 'hash': resp['promo_data']['hash']}
            )
        )
        impression = self.promo.impressions.first()
        self.assertEqual(impression.offers, 1)
        self.assertEqual(impression.views, 1)
        self.assertEqual(impression.clicks, 1)

    def test_footer_setting(self):
        """Test that the promo doesn't show with USE_PROMOS is False"""
        with self.settings(USE_PROMOS=False):
            r = self.client.get(
                '/api/v2/footer_html/?project=pip&version=latest&page=index'
            )
            resp = json.loads(r.content)
            self.assertEqual(resp['promo'], False)

    def test_footer_no_obj(self):
        """Test that the promo doesn't get set with no SupporterPromo objects"""
        self.promo.delete()
        r = self.client.get(
            '/api/v2/footer_html/?project=pip&version=latest&page=index'
        )
        resp = json.loads(r.content)
        self.assertEqual(resp['promo'], False)

    def test_project_disabling(self):
        """Test that the promo doesn't show when the project has it disabled"""
        self.pip.allow_promos = False
        self.pip.save()
        r = self.client.get(
            '/api/v2/footer_html/?project=pip&version=latest&page=index'
        )
        resp = json.loads(r.content)
        self.assertEqual(resp['promo'], False)


class FilterTests(TestCase):

    def setUp(self):
        us = get(Country, country='US')
        ca = get(Country, country='CA')
        mx = get(Country, country='MX')
        az = get(Country, country='AZ')
        # Only show in US,CA
        self.promo = get(SupporterPromo,
                         slug='promo-slug',
                         link='http://example.com',
                         image='http://media.example.com/img.png')
        self.filter = get(GeoFilter,
                          promo=self.promo,
                          countries=[us, ca, mx],
                          filter_type=INCLUDE,
                          )

        # Don't show in AZ
        self.promo2 = get(SupporterPromo,
                          slug='promo2-slug',
                          link='http://example.com',
                          image='http://media.example.com/img.png')
        self.filter2 = get(GeoFilter,
                           promo=self.promo2,
                           countries=[az],
                           filter_type=EXCLUDE,
                           )

        self.pip = get(Project, slug='pip', allow_promos=True)

    def test_include(self):
        # US view
        ret = show_to_geo(self.promo, 'US')
        self.assertEqual(ret, True)

    def test_exclude(self):
        # Az -- don't show AZ ad
        ret = show_to_geo(self.promo2, 'AZ')
        self.assertEqual(ret, False)

    def test_failed_filter(self):
        # Random Country -- don't show "only US" ad
        ret = show_to_geo(self.promo, 'FO')
        self.assertEqual(ret, False)

        ret2 = show_to_geo(self.promo2, 'FO')
        self.assertEqual(ret2, True)
