Feature: Delayed payment status is clear and safe
  @mobile
  Scenario Outline: Delayed status is localized and refresh never resubmits
    Given an awaiting test payment is displayed in "<language>"
    When the backend resolves the test payment as "<outcome>"
    Then manual refresh shows "<title>" without another payment
    And delayed details survive language switch and reload

    Examples:
      | language | outcome   | title                           |
      | en       | confirmed | Payment confirmed               |
      | ja       | confirmed | お支払いを確認しました           |
      | en       | expired   | Payment request expired         |
      | ja       | expired   | 支払いリクエストの期限が切れました |
      | en       | cancelled | Payment request cancelled       |
      | ja       | cancelled | 支払いリクエストはキャンセルされました |

  Scenario: Failed status refresh preserves last known evidence
    Given an awaiting test payment is displayed in "en"
    Then a failed refresh preserves the reference and offers another check
