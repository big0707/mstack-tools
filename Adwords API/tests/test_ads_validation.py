from adwords_agent.ads import validate_create_request, validate_update_request
from adwords_agent.models import CreateResponsiveSearchAdRequest, TextAssetSpec, UpdateResponsiveSearchAdRequest


def test_create_rsa_requires_minimum_assets() -> None:
    request = CreateResponsiveSearchAdRequest(
        customer_id="123",
        ad_group_id="456",
        final_urls=[],
        headlines=[TextAssetSpec("one")],
        descriptions=[TextAssetSpec("one")],
    )

    errors = validate_create_request(request)

    assert "at least 3 headlines" in " ".join(errors)
    assert "at least 2 descriptions" in " ".join(errors)
    assert "at least 1 final URL" in " ".join(errors)


def test_update_rsa_rejects_empty_update() -> None:
    request = UpdateResponsiveSearchAdRequest(customer_id="123", ad_id="456")

    errors = validate_update_request(request)

    assert errors == ["No update fields were provided."]
