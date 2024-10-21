### Deployment Results {{ ":rocket:" if status === "success" else ":cry:" }}

{{ actor }} deployed branch `{{ ref }}` to the **{{ environment }}** environment. This deployment was a {{ status }} {{ ":rocket:" if status === "success" else ":cry:" }}.
