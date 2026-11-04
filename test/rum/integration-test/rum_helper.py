import requests

RUM_MARKERS = ["datadoghq-browser-sdk", "DD_RUM"]


def assert_rum_injected(response: requests.Response) -> None:
    content = response.text
    found_markers = [marker for marker in RUM_MARKERS if marker in content]
    assert found_markers, (
        f"Expected RUM SDK to be injected but found no markers. "
        f"Response length: {len(content)}, "
        f"Content preview: {content[:200]}"
    )

    injection_header = response.headers.get("x-datadog-sdk-injected")
    assert injection_header == "1", (
        f"Expected x-datadog-sdk-injected header to be '1' but got '{injection_header}'"
    )


def assert_rum_not_injected(response: requests.Response) -> None:
    content = response.text
    found_markers = [marker for marker in RUM_MARKERS if marker in content]
    assert not found_markers, (
        f"Expected RUM SDK NOT to be injected but found markers: {found_markers}. "
        f"Content preview: {content[:500]}"
    )

    injection_header = response.headers.get("x-datadog-sdk-injected")
    assert injection_header != "1", (
        f"Expected x-datadog-sdk-injected header NOT to be '1' but got '{injection_header}'"
    )
