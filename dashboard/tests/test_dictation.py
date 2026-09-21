import base64
import datetime as dt
import json
import urllib.error
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from dashboard.models import Meal, SourceSubmission
from dashboard.services.ai import AIUnavailable, MAX_AUDIO_BYTES, transcribe_audio


def audio(content=b'\x1aE\xdf\xa3audio', content_type='audio/webm;codecs=opus'):
    return SimpleUploadedFile('dictado.webm', content, content_type=content_type)


@override_settings(OPENROUTER_API_KEY='test-key', OPENROUTER_TRANSCRIPTION_MODEL='openai/whisper-large-v3')
class TranscriptionServiceTests(SimpleTestCase):
    @patch('dashboard.services.ai.urllib.request.urlopen')
    def test_openrouter_contract_and_spanish_transcript(self, urlopen):
        urlopen.return_value.__enter__.return_value.read.return_value = json.dumps({'text': '  Dos huevos con arroz.  '}).encode()
        self.assertEqual(transcribe_audio(audio()), 'Dos huevos con arroz.')
        request = urlopen.call_args.args[0]
        self.assertTrue(request.full_url.endswith('/audio/transcriptions'))
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-key')
        payload = json.loads(request.data)
        self.assertEqual(payload['model'], 'openai/whisper-large-v3')
        self.assertEqual(payload['language'], 'es')
        self.assertEqual(payload['input_audio']['format'], 'webm')
        self.assertEqual(base64.b64decode(payload['input_audio']['data']), b'\x1aE\xdf\xa3audio')

    @patch('dashboard.services.ai.urllib.request.urlopen')
    def test_invalid_uploads_never_reach_provider(self, urlopen):
        oversized = audio()
        oversized.size = MAX_AUDIO_BYTES + 1
        for upload in [None, audio(b''), audio(content_type='text/plain'), oversized]:
            with self.subTest(upload=upload), self.assertRaises(ValueError):
                transcribe_audio(upload)
        urlopen.assert_not_called()

    @override_settings(OPENROUTER_API_KEY='')
    def test_missing_key(self):
        with self.assertRaises(AIUnavailable):
            transcribe_audio(audio())

    @patch('dashboard.services.ai.urllib.request.urlopen')
    def test_malformed_and_empty_responses(self, urlopen):
        for response in [b'not json', b'[]', b'{}', b'{"text": " "}', b'{"text": 1}']:
            urlopen.return_value.__enter__.return_value.read.return_value = response
            with self.subTest(response=response), self.assertRaises(AIUnavailable):
                transcribe_audio(audio())

    @patch('dashboard.services.ai.urllib.request.urlopen')
    def test_provider_errors_are_safe(self, urlopen):
        for error in [TimeoutError(), urllib.error.URLError('offline'), urllib.error.HTTPError('https://example.test', 429, 'rate limited', {}, None)]:
            urlopen.side_effect = error
            with self.subTest(error=error), self.assertRaises(AIUnavailable):
                transcribe_audio(audio())


class DictationViewTests(TestCase):
    def setUp(self):
        self.url = reverse('dashboard:module', args=(dt.date(2099, 12, 30).isoformat(), 'nutrition'))
        self.user = get_user_model().objects.create_user('dictation', password='test-password-123')
        self.client.force_login(self.user)

    @patch('dashboard.views.transcribe_audio', return_value='Dos huevos con arroz')
    def test_transcription_does_not_save_meal(self, transcribe):
        response = self.client.post(self.url, {'action': 'meal-transcribe', 'audio': audio()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['text'], 'Dos huevos con arroz')
        self.assertFalse(Meal.objects.exists())
        self.assertFalse(SourceSubmission.objects.exists())
        transcribe.assert_called_once()

    def test_missing_audio_is_validation_error(self):
        response = self.client.post(self.url, {'action': 'meal-transcribe'})
        self.assertEqual(response.status_code, 422)

    @patch('dashboard.views.transcribe_audio', side_effect=AIUnavailable('Reintenta'))
    def test_service_failure(self, transcribe):
        response = self.client.post(self.url, {'action': 'meal-transcribe', 'audio': audio()})
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()['ok'])

    @patch('dashboard.views.transcribe_audio')
    def test_authentication_required(self, transcribe):
        self.client.logout()
        self.assertEqual(self.client.post(self.url, {'action': 'meal-transcribe', 'audio': audio()}).status_code, 302)
        transcribe.assert_not_called()

    @patch('dashboard.views.request_structured_json', return_value={'data': {'foods': [], 'notes': 'Arroz'}, 'model': 'test-model'})
    def test_dictated_text_and_image_use_existing_preview(self, generate):
        for fields in [{'ai_description': 'Dos huevos con arroz'}, {'photo': SimpleUploadedFile('meal.png', b'photo', content_type='image/png')}]:
            response = self.client.post(self.url, {'action': 'meal-ai-preview', **fields})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(generate.call_count, 2)
        self.assertFalse(Meal.objects.exists())

    def test_three_input_options_render(self):
        response = self.client.get(self.url)
        for mode in ['text', 'voice', 'image']:
            self.assertContains(response, f'data-meal-source="{mode}"')
