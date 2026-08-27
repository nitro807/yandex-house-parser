import unittest

from app.extract import (
    address_matches,
    inside_url_for_house,
    organization_from_dom,
    organization_from_node,
    organizations_from_payloads,
)

class ExtractTests(unittest.TestCase):
    def test_builds_inside_url_only_for_house_page(self):
        house = "https://yandex.com/maps/213/moscow/house/example/abc==/?ll=1%2C2#map"
        self.assertEqual(
            inside_url_for_house(house),
            "https://yandex.com/maps/213/moscow/house/example/abc==/inside/?ll=1%2C2",
        )
        self.assertIsNone(inside_url_for_house("https://yandex.com/maps/org/ozon/11633193053/"))

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

    def test_known_house_rejects_business_without_address(self):
        self.assertFalse(address_matches(None, "Москва, Тверская улица, 1"))

    def test_trusted_house_section_accepts_business_without_address(self):
        self.assertTrue(address_matches(None, "Москва, Тверская улица, 1", allow_missing_candidate=True))

    def test_payload_rejects_nearby_and_addressless_businesses(self):
        payload = {
            "items": [
                {"type": "business", "id": "1", "title": "В доме", "address": "Москва, Тверская улица, 1"},
                {"type": "business", "id": "2", "title": "Рядом", "address": "Москва, Тверская улица, 10"},
                {"type": "business", "id": "3", "title": "Метка на карте"},
            ]
        }
        result = organizations_from_payloads([payload], "Москва, Тверская улица, 1")
        self.assertEqual([organization.id for organization in result], ["1"])

    def test_house_section_keeps_addressless_but_rejects_other_address(self):
        payload = {
            "items": [
                {"type": "business", "id": "1", "title": "Ozon"},
                {"type": "business", "id": "2", "title": "Рядом", "address": "Москва, Тверская улица, 10"},
            ]
        }
        result = organizations_from_payloads(
            [payload], "Москва, Тверская улица, 1", allow_missing_address=True
        )
        self.assertEqual([organization.id for organization in result], ["1"])

    def test_gallery_link_is_not_an_organization(self):
        result = organization_from_dom(
            "Фото",
            "/maps/org/ozon/11633193053/gallery/",
            "Фото",
        )
        self.assertIsNone(result)

    def test_canonical_org_link_uses_explicit_card_fields(self):
        result = organization_from_dom(
            "Ozon",
            "/maps/org/ozon/11633193053/",
            "Ozon\nОткрыто до 22:00\nПункт выдачи",
            category="Пункт выдачи",
            address="Шебашёвский пр., 7",
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.id, "11633193053")
        self.assertEqual(result.name, "Ozon")
        self.assertEqual(result.category, "Пункт выдачи")
        self.assertEqual(result.address, "Шебашёвский пр., 7")

    def test_opening_hours_are_not_mistaken_for_address(self):
        result = organization_from_dom(
            "Ozon",
            "/maps/org/ozon/11633193053/",
            "Ozon\nФото\nОткрыто до 22:00\nПункт выдачи",
            category="Пункт выдачи",
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIsNone(result.address)

    def test_floor_and_office_are_not_mistaken_for_house_address(self):
        result = organization_from_dom(
            "Алина Айз",
            "/maps/org/alina_ayz/237258866285/",
            "Алина Айз\nОткрыто до 21:00\nСалон бровей и ресниц\n"
            "Вход со стороны улицы, этаж цокольный, кабинет 8",
            category="Салон бровей и ресниц",
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.name, "Алина Айз")
        self.assertIsNone(result.address)


if __name__ == "__main__":
    unittest.main()
