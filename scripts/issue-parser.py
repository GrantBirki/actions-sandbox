
import json
import os
print("Hello World!")

"""
##### For local testing #####

# Opening JSON file
f = open('./scripts/sample-issue.json', 'r')

data = json.load(f)
f.close()

#  "body": "### Model Name\r\n\r\nmy cool molecule\r\n\r\n### Model Description\r\n\r\nThis is a prediction for a super cool molecule\r\n\r\n### Ersilia ID\r\n\r\neos11aa\r\n\r\n### Publication\r\n\r\nThe following link is just an example:\r\n\r\nwww.example.com\r\n\r\n### Code\r\n\r\n_No response_\r\n\r\n### License\r\n\r\n_No response_",

issue_body = data["github"]["payload"]["issue"]["body"]

##### For local testing #####

"""

print(os.getenv("ISSUE_BODY"))
issue_body = os.getenv("ISSUE_BODY")

# TODO: Maybe try using a regex
# TODO: pull keys from the issue template
issue_body_sections_list = issue_body.split("###")[1:]
print(issue_body_sections_list)

parsed_issue_body_dict = {}

for issue_body_section in issue_body_sections_list:
    issue_body = issue_body_section.split("\r\n\r", 1)

    key = issue_body[0].strip().lower().replace(" ", "-")
    value = issue_body[1].strip()

    if value == '_No response_':
        value = None

    parsed_issue_body_dict[key] = value

print(parsed_issue_body_dict)
# TODO: validations
# TODO: move this all into a function haha
