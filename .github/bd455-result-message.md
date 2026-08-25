### BD455 inherited template

Outcome: {{ status }}

Environment: {{ environment }}

Admitted commit: {{ sha }}

{% if environment_url !== null %}[Fixture environment]({{ environment_url }}){% endif %}

{{ results }}
