### Deployment Results {{ ":rocket:" if status === "success" else ":cry:" }}

{{ actor }} deployed branch `{{ ref }}` to the **{{ environment }}** environment. This deployment was a {{ status }} {{ ":rocket:" if status === "success" else ":cry:" }}.

<details>
  <summary>Deployment Details</summary>

  - deployment_id: `{{ deployment_id }}`
  - sha: `{{ sha }}`
  - params: `{{ params }}`
  - parsed_params: `{{ parsed_params | safe }}`
  - deployment_end_time: `{{ deployment_end_time }}`
  - ref: `{{ ref }}`
  - approved_reviews_count: `{{ approved_reviews_count }}`

</details>
