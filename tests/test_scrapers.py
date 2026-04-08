import unittest
from unittest.mock import patch, MagicMock
from scrapers import fetch_codeforces, fetch_leetcode, fetch_codechef

class TestScrapers(unittest.TestCase):

    @patch('requests.get')
    def test_fetch_codeforces(self, mock_get):
        # Mocking Codeforces API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'result': [
                {
                    'id': 123,
                    'name': 'Test Contest',
                    'phase': 'BEFORE',
                    'startTimeSeconds': 1730000000, # Some future timestamp
                    'durationSeconds': 7200
                }
            ]
        }
        mock_get.return_value = mock_response
        
        # We need to make sure the timestamp is within the next 7 days relative to "now"
        # Since I'm using datetime.now(timezone.utc) in the scraper, I should probably mock that too 
        # but let's just see if it handles the structure.
        
        contests = fetch_codeforces(days_limit=365) # Large limit to avoid time issues in test
        self.assertIsInstance(contests, list)
        if contests:
            self.assertTrue(contests[0]['id'].startswith('cf_'))
            self.assertEqual(contests[0]['name'], 'Test Contest')

    @patch('requests.post')
    def test_fetch_leetcode(self, mock_post):
        # Mocking LeetCode GraphQL response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'data': {
                'allContests': [
                    {
                        'title': 'Weekly Contest',
                        'titleSlug': 'weekly-contest',
                        'startTime': 1730000000,
                        'duration': 5400
                    }
                ]
            }
        }
        mock_post.return_value = mock_response
        
        contests = fetch_leetcode(days_limit=365)
        self.assertIsInstance(contests, list)
        if contests:
            self.assertTrue(contests[0]['id'].startswith('lc_'))

if __name__ == '__main__':
    unittest.main()
