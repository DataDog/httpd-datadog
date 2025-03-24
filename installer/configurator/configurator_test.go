// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache 2.0 License. This product includes software developed at
// Datadog (https://www.datadoghq.com/).
//
// Copyright 2024-Present Datadog, Inc.

package main

import (
	"strings"
	"testing"
)

func TestValidateInput(t *testing.T) {
	tests := []struct {
		name                    string
		proxyKind               string
		appID                   string
		site                    string
		clientToken             string
		arch                    string
		sessionSampleRate       int
		sessionReplaySampleRate int
		remoteConfigurationId   string
		expectedError           string
	}{
		{
			name:                    "Valid input",
			proxyKind:               "nginx",
			appID:                   "test-app",
			site:                    "test-site",
			clientToken:             "test-token",
			arch:                    "amd64",
			sessionSampleRate:       50,
			sessionReplaySampleRate: 50,
			remoteConfigurationId:   "",
			expectedError:           "",
		},
		{
			name:                    "Empty appID",
			proxyKind:               "nginx",
			appID:                   "",
			site:                    "test-site",
			clientToken:             "test-token",
			arch:                    "amd64",
			sessionSampleRate:       50,
			sessionReplaySampleRate: 50,
			remoteConfigurationId:   "",
			expectedError:           "--appId is required",
		},
		{
			name:                    "Empty site",
			proxyKind:               "nginx",
			appID:                   "test-app",
			site:                    "",
			clientToken:             "test-token",
			arch:                    "amd64",
			sessionSampleRate:       50,
			sessionReplaySampleRate: 50,
			remoteConfigurationId:   "",
			expectedError:           "--site is required",
		},
		{
			name:                    "Empty clientToken",
			proxyKind:               "nginx",
			appID:                   "test-app",
			site:                    "test-site",
			clientToken:             "",
			arch:                    "amd64",
			sessionSampleRate:       50,
			sessionReplaySampleRate: 50,
			remoteConfigurationId:   "",
			expectedError:           "--clientToken is required",
		},
		{
			name:                    "Invalid sessionSampleRate (negative)",
			proxyKind:               "nginx",
			appID:                   "test-app",
			site:                    "test-site",
			clientToken:             "test-token",
			arch:                    "amd64",
			sessionSampleRate:       -1,
			sessionReplaySampleRate: 50,
			remoteConfigurationId:   "",
			expectedError:           "sessionSampleRate is required and must be between 0 and 100",
		},
		{
			name:                    "Invalid sessionSampleRate (over 100)",
			proxyKind:               "nginx",
			appID:                   "test-app",
			site:                    "test-site",
			clientToken:             "test-token",
			arch:                    "amd64",
			sessionSampleRate:       101,
			sessionReplaySampleRate: 50,
			remoteConfigurationId:   "",
			expectedError:           "sessionSampleRate is required and must be between 0 and 100",
		},
		{
			name:                    "Invalid sessionReplaySampleRate (negative)",
			proxyKind:               "nginx",
			appID:                   "test-app",
			site:                    "test-site",
			clientToken:             "test-token",
			arch:                    "amd64",
			sessionSampleRate:       50,
			sessionReplaySampleRate: -1,
			remoteConfigurationId:   "",
			expectedError:           "sessionReplaySampleRate is required and must be between 0 and 100",
		},
		{
			name:                    "Invalid sessionReplaySampleRate (over 100)",
			proxyKind:               "nginx",
			appID:                   "test-app",
			site:                    "test-site",
			clientToken:             "test-token",
			arch:                    "amd64",
			sessionSampleRate:       50,
			sessionReplaySampleRate: 101,
			remoteConfigurationId:   "",
			expectedError:           "sessionReplaySampleRate is required and must be between 0 and 100",
		},
		{
			name:                    "Invalid arch",
			proxyKind:               "nginx",
			appID:                   "test-app",
			site:                    "test-site",
			clientToken:             "test-token",
			arch:                    "x86",
			sessionSampleRate:       50,
			sessionReplaySampleRate: 50,
			remoteConfigurationId:   "",
			expectedError:           "arch must be either 'amd64' or 'arm64'",
		},
		{
			name:                    "Valid input with arm64 arch",
			proxyKind:               "nginx",
			appID:                   "test-app",
			site:                    "test-site",
			clientToken:             "test-token",
			arch:                    "arm64",
			sessionSampleRate:       50,
			sessionReplaySampleRate: 50,
			remoteConfigurationId:   "",
			expectedError:           "",
		},
		{
			name:                    "Valid input with httpd proxy kind",
			proxyKind:               "httpd",
			appID:                   "test-app",
			site:                    "test-site",
			clientToken:             "test-token",
			arch:                    "amd64",
			sessionSampleRate:       50,
			sessionReplaySampleRate: 50,
			remoteConfigurationId:   "",
			expectedError:           "",
		},
		{
			name:                    "Invalid proxy kind",
			proxyKind:               "iis",
			appID:                   "test-app",
			site:                    "test-site",
			clientToken:             "test-token",
			arch:                    "amd64",
			sessionSampleRate:       50,
			sessionReplaySampleRate: 50,
			remoteConfigurationId:   "",
			expectedError:           "proxyKind must be either 'nginx' or 'httpd', found 'iis'",
		},
		{
			name:                    "Remote config OK",
			proxyKind:               "nginx",
			appID:                   "test-app",
			site:                    "test-site",
			clientToken:             "test-token",
			arch:                    "amd64",
			sessionSampleRate:       -1,
			sessionReplaySampleRate: -1,
			remoteConfigurationId:   "123",
			expectedError:           "",
		},
		{
			name:                    "No local and remote configuration",
			proxyKind:               "nginx",
			appID:                   "test-app",
			site:                    "test-site",
			clientToken:             "test-token",
			arch:                    "amd64",
			sessionSampleRate:       50,
			sessionReplaySampleRate: 50,
			remoteConfigurationId:   "123",
			expectedError:           "ArgumentError: unable to set both remote configuration and local configuration",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateInput(tt.proxyKind, tt.appID, tt.site, tt.clientToken, tt.arch, tt.remoteConfigurationId, tt.sessionSampleRate, tt.sessionReplaySampleRate)

			if tt.expectedError == "" {
				if err != nil {
					t.Errorf("Expected no error, but got: %v", err)
				}
			} else {
				if err == nil {
					t.Errorf("Expected error containing '%s', but got no error", tt.expectedError)
				} else if !strings.Contains(err.Error(), tt.expectedError) {
					t.Errorf("Expected error containing '%s', but got: %v", tt.expectedError, err)
				}
			}
		})
	}
}
