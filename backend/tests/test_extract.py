import unittest

from app.extract import address_matches, organization_from_node, organizations_from_payloads

class ExtractTests(unittest.TestCase):
    def test_extracts_current_yandex_business_shape(self):
        payload = {"data": {"items": [{"type": "business", "id": "123", "title": "Кофейня", "address": "Москва, Тверская улица, 1", "categories": [{"name": "Кофейня"}], "phones": [{"value": "+7 999 123-45-67"}], "ratingData": {"ratingValue": 4.8}}]}}
        result = organizations_from_payloads([payload], "Москва, ул. Тверская, д. 1")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "123")
        self.assertEqual(result[0].rating, 4.8)
        self.assertEqual(result[0].phones, ["+7 999 123-45-67"])

    def test_extracts_official_geojson_shape(self):
        node = {"type": "Feature", "properties": {"uri": "ymapsbm1://org?oid=987", "CompanyMetaData": {"id": "987", "name": "Аптека", "address": "Москва, Арбат, 10", "Categories": [{"name": "Аптека"}], "Phones": [{"formatted": "+7 495 000-00-00"}]}}}
        result = organization_from_node(node)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.name, "Аптека")
        self.assertTrue(result.yandex_url and result.yandex_url.endswith("/987/"))

    def test_address_normalization_tolerates_abbreviations(self):
        self.assertTrue(address_matches("г. Москва, ул. Тверская, дом 1", "Москва, Тверская улица, 1"))
        self.assertFalse(address_matches("Москва, Тверская улица, 10", "Москва, Тверская улица, 1"))


if __name__ == "__main__":
    unittest.main()
