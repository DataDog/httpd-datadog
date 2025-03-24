#!/usr/bin/env python3
# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache 2.0 License. This product includes software developed at
# Datadog (https://www.datadoghq.com/).
#
# Copyright 2024-Present Datadog, Inc.

import re
import typing

from dataclasses import dataclass
from typing import Dict

@dataclass(frozen=True)
class ThirdParty:
    component: str
    origin: str
    license: str
    copyright: str

def manual_mappings(deps) -> typing.Dict[str, ThirdParty]:
    result = {}

    for component, dep in deps.items():
        lic = dep.license if dep.license != [''] and dep.license != [] else f"['{map_licenses(component)}']"
        cop = dep.copyright if dep.copyright != [''] and dep.copyright != [] else f"['{map_copyright(component)}']"
        result[component] = ThirdParty(
            component=component,
            origin=dep.origin,
            license=lic,
            copyright=cop,
        )

    return result

def map_licenses(component):
    license_mappings = {
        "org.apache.maven.plugins:maven-assembly-plugin": "Apache-2.0",
        "org.sitemesh:sitemesh": "Apache-2.0",
        "check_conf": "Apache-2.0",
    }

    if component in license_mappings:
        return license_mappings.get(component)

    if re.search("datadog", component, re.IGNORECASE) or re.search("inject-browser-sdk", component, re.IGNORECASE):
        return "Apache-2.0"
    if re.search("golang.org", component, re.IGNORECASE) or re.search("gopkg", component, re.IGNORECASE):
        return "Apache-2.0"
    if re.search("opentelemetry", component, re.IGNORECASE):
        return "Apache-2.0"

    raise Exception(f"License not found for {component}")

def map_copyright(component):
    copyright_mappings = {
        "org.apache.maven.plugins:maven-assembly-plugin": "The Apache Software Foundation",
        "org.junit.jupiter:junit-jupiter-api": "The JUnit Team",
        "org.sitemesh:sitemesh": "The OpenSymphony Group",
        "check_conf": "Datadog, Inc.",
    }

    if component in copyright_mappings:
        return copyright_mappings.get(component)
    
    if re.search("datadog", component, re.IGNORECASE) or re.search("inject-browser-sdk", component, re.IGNORECASE):
        return "Datadog, Inc."
    if re.search("opentelemetry", component, re.IGNORECASE):
        return "OpenTelemetry"
    if re.search("golang.org", component, re.IGNORECASE) or re.search("gopkg", component, re.IGNORECASE):
        return "The Go Authors"
    if re.search("k8s.io", component, re.IGNORECASE):
        return "The Kubernetes Authors"

    raise Exception(f"Copyright not found for {component}")

def merge_dependencies(deps_license, new_deps) -> Dict[str, ThirdParty]:
    for key, new_dep in new_deps.items():
        if key not in deps_license:
            deps_license[key] = new_dep
        else:
            existing_dep = deps_license[key]

            existing_license = str(existing_dep.license)
            new_license = str(new_dep.license)
            existing_copyright = str(existing_dep.copyright)
            new_copyright = str(new_dep.copyright)

            deps_license[key] = ThirdParty(
                component=existing_dep.component,
                origin=max(existing_dep.origin, new_dep.origin, key=len),
                license=max(existing_license, new_license, key=len),
                copyright=max(existing_copyright, new_copyright, key=len)
            )
    return deps_license
