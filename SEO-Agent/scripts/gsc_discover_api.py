#!/usr/bin/env python3
"""
Try crawl error endpoints with URL-prefix property format 
and also check if urlCrawlErrorsCounts is still alive.
Also check the discovery doc for available methods.
"""

import json
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

KEY_FILE = "credentials/gsc-key.json"

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/webmasters",
]

def main():
    credentials = service_account.Credentials.from_service_account_file(
        KEY_FILE, scopes=SCOPES
    )
    session = AuthorizedSession(credentials)
    
    # Check discovery doc for available methods
    print("=== Webmasters v3 Discovery - methods ===")
    resp = session.get("https://www.googleapis.com/discovery/v1/apis/webmasters/v3/rest")
    if resp.status_code == 200:
        doc = resp.json()
        for resource_name, resource in doc.get("resources", {}).items():
            print(f"\nResource: {resource_name}")
            for method_name, method in resource.get("methods", {}).items():
                print(f"  - {method_name}: {method.get('httpMethod')} {method.get('path')}")
    
    print("\n\n=== SearchConsole v1 Discovery ===")
    resp = session.get("https://searchconsole.googleapis.com/$discovery/rest?version=v1")
    if resp.status_code == 200:
        doc = resp.json()
        for resource_name, resource in doc.get("resources", {}).items():
            print(f"\nResource: {resource_name}")
            for method_name, method in resource.get("methods", {}).items():
                print(f"  - {method_name}: {method.get('httpMethod')} {method.get('path', method.get('flatPath', ''))}")
            # Check nested resources
            for sub_name, sub_resource in resource.get("resources", {}).items():
                print(f"  Sub-resource: {sub_name}")
                for method_name, method in sub_resource.get("methods", {}).items():
                    print(f"    - {method_name}: {method.get('httpMethod')} {method.get('path', method.get('flatPath', ''))}")

if __name__ == "__main__":
    main()
