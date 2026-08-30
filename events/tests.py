from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Event, Reservation


class EventModelTests(APITestCase):
    def setUp(self):
        self.event = Event.objects.create(
            title="PyCon India 2025",
            venue="NIMHANS Convention Centre, Bangalore",
            date="2025-09-20",
            total_seats=5,
            available_seats=5,
            status="upcoming",
        )

    def test_create_event(self):
        url = reverse('event-list')
        data = {
            "title": "DjangoCon 2025",
            "venue": "Mumbai",
            "date": "2025-11-01",
            "total_seats": 100,
            "available_seats": 100,
            "status": "upcoming",
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Event.objects.count(), 2)

    def test_create_event_rejects_available_seats_greater_than_total(self):
        url = reverse('event-list')
        data = {
            "title": "Bad Event",
            "venue": "Delhi",
            "date": "2025-11-01",
            "total_seats": 10,
            "available_seats": 20,
            "status": "upcoming",
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_events(self):
        url = reverse('event-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(len(response.data['results']), 1)

    def test_filter_events_by_status(self):
        Event.objects.create(
            title="Completed Event", venue="Pune", date="2024-01-01",
            total_seats=10, available_seats=10, status="completed",
        )
        response = self.client.get(reverse('event-list'), {'status': 'upcoming'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['title'], "PyCon India 2025")

    def test_filter_events_by_venue(self):
        response = self.client.get(reverse('event-list'), {'venue': 'bangalore'})
        self.assertEqual(response.data['count'], 1)

        response = self.client.get(reverse('event-list'), {'venue': 'nowhere'})
        self.assertEqual(response.data['count'], 0)

    def test_reservations_count_field(self):
        Reservation.objects.create(
            event=self.event, attendee_name="A", attendee_email="a@example.com",
            seats_reserved=1, status="confirmed",
        )
        Reservation.objects.create(
            event=self.event, attendee_name="B", attendee_email="b@example.com",
            seats_reserved=1, status="cancelled",
        )
        response = self.client.get(reverse('event-detail', args=[self.event.id]))
        self.assertEqual(response.data['reservations_count'], 1)


class ReservationTests(APITestCase):
    def setUp(self):
        self.event = Event.objects.create(
            title="PyCon India 2025",
            venue="Bangalore",
            date="2025-09-20",
            total_seats=5,
            available_seats=5,
            status="upcoming",
        )

    def _reserve(self, seats, attendee_name="Priya Sharma"):
        return self.client.post(
            reverse('reservation-list'),
            {
                "event": self.event.id,
                "attendee_name": attendee_name,
                "attendee_email": "priya@example.com",
                "seats_reserved": seats,
            },
            format='json',
        )

    def test_create_reservation_deducts_seats(self):
        response = self._reserve(2)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'confirmed')

        self.event.refresh_from_db()
        self.assertEqual(self.event.available_seats, 3)

    def test_overbooking_returns_400(self):
        response = self._reserve(10)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.event.refresh_from_db()
        self.assertEqual(self.event.available_seats, 5)

    def test_seats_reserved_must_be_at_least_one(self):
        response = self._reserve(0)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_reserve_for_non_upcoming_or_ongoing_event(self):
        self.event.status = 'completed'
        self.event.save()
        response = self._reserve(1)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_reservations_by_event_id(self):
        other_event = Event.objects.create(
            title="Other Event", venue="Delhi", date="2025-10-01",
            total_seats=10, available_seats=10, status="upcoming",
        )
        self._reserve(1)
        self.client.post(
            reverse('reservation-list'),
            {
                "event": other_event.id,
                "attendee_name": "Someone Else",
                "attendee_email": "other@example.com",
                "seats_reserved": 1,
            },
            format='json',
        )

        response = self.client.get(reverse('reservation-list'), {'event_id': self.event.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['event'], self.event.id)

    def test_cancel_reservation_restores_seats(self):
        create_response = self._reserve(2)
        reservation_id = create_response.data['id']

        response = self.client.post(reverse('reservation-cancel', args=[reservation_id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'cancelled')

        self.event.refresh_from_db()
        self.assertEqual(self.event.available_seats, 5)

    def test_cancel_already_cancelled_reservation_returns_400(self):
        create_response = self._reserve(1)
        reservation_id = create_response.data['id']

        self.client.post(reverse('reservation-cancel', args=[reservation_id]))
        response = self.client.post(reverse('reservation-cancel', args=[reservation_id]))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
