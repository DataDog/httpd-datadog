Import-Module WebAdministration

<#
.SYNOPSIS
    Migrates RUM configuration from JSON into IIS Site or Application web.config

.DESCRIPTION
    The script converts JSON RUM configuration settings from Datadog's
    directories into IIS Site or Application configurations. 
#>
function Migrate-Datadog-RUMConfiguration {
    function Migrate-Directory {
        param (
            [Parameter(Mandatory=$true)]
            [string]$DirectoryPath,
            
            [Parameter(Mandatory=$true)]
            [string]$CurrentPath
        )

        $configPath = Join-Path $DirectoryPath "rum-config.json"
        Write-Host "Migrating configuration for site $CurrentPath from $configPath"
        if (Test-Path $configPath) {
            $config = Get-Content $configPath | ConvertFrom-Json
            if ($config.rum) {
                $RUMConfig = @{
                    IISSite = $CurrentPath
                    ApplicationId = $config.rum.applicationId
                    ClientToken = $config.rum.clientToken
                }

                if ($config.rum.PSObject.Properties.Name -contains "site") {
                    $RUMConfig.DatadogSite = $config.rum.site
                }
                if ($config.rum.PSObject.Properties.Name -contains "sessionSampleRate") {
                    $RUMConfig.SessionSampleRate = $config.rum.sessionSampleRate
                }
                if ($config.rum.PSObject.Properties.Name -contains "sessionReplaySampleRate") {
                    $RUMConfig.SessionReplaySampleRate = $config.rum.sessionReplaySampleRate
                }
                if ($config.rum.PSObject.Properties.Name -contains "service") {
                    $RUMConfig.Service = $config.rum.service
                }

                New-Datadog-RUMConfiguration @RUMConfig
            }
        }

        $subDirs = Get-ChildItem -Path $DirectoryPath -Directory
        foreach ($subDir in $subDirs) {
            $newPath = "$CurrentPath/$($subDir.Name)"
            Migrate-Directory -DirectoryPath $subDir.FullName -CurrentPath $newPath
        }
    }

    $registryPath = "HKLM:\Software\DataDog\Datadog RUM"
    $defaultConfigPath = "C:\ProgramData\Datadog RUM\"

    if (Test-Path -Path $registryPath) {
        $configDir = Get-ItemPropertyValue -Path $registryPath -Name "ConfigRoot" -ErrorAction SilentlyContinue
        if (-not $configDir) {
            Write-Host "ConfigRoot value not found in registry. Using default path: $defaultConfigPath"
            $configDir = $defaultConfigPath
        }
    } else {
        Write-Host "The registry key '$registryPath' doesn't exist. Using default path: $defaultConfigPath"
        $configDir = $defaultConfigPath
    }

    if (Test-Path -Path $configDir) {
        $sites = Get-ChildItem -Path $configDir -Directory
        foreach ($site in $sites) {
            Migrate-Directory -DirectoryPath $site.FullName -CurrentPath $site.Name
        }
    } else {
        Write-Warning "Configuration directory '$configDir' doesn't exist. No sites to migrate."
    }
}

<#
.SYNOPSIS
Removes Datadog RUM configuration from all IIS sites and applications.

.DESCRIPTION
The Uninstall-Datadog-RUMConfiguration function removes Datadog RUM configuration
from all IIS sites and their nested applications at any depth.
#>
function Uninstall-Datadog-RUMConfiguration {
    function Remove-DatadogRumFromApp {
        param (
            [string]$SiteName,
            [string]$AppPath
        )
        
        $sectionPath = "system.webServer/datadogRum"
        $psPath = "MACHINE/WEBROOT/APPHOST/$SiteName$AppPath"
    
        if (Get-WebConfiguration -Filter $sectionPath -PSPath $psPath -ErrorAction SilentlyContinue) {
            try {
                Start-WebCommitDelay
    
                $options = Get-WebConfiguration -PSPath $psPath -Filter "$sectionPath/option" -ErrorAction SilentlyContinue
                foreach ($option in $options) {
                    Clear-WebConfiguration -PSPath $psPath -Filter "$sectionPath/option[@name='$($option.name)']" -ErrorAction SilentlyContinue
                }
                Clear-WebConfiguration -PSPath $psPath -Filter $sectionPath -ErrorAction SilentlyContinue
    
                Stop-WebCommitDelay -Commit $True
                Write-Host "Successfully removed Datadog RUM configuration from '$SiteName$AppPath'"
            }
            catch {
                Stop-WebCommitDelay
                Write-Warning "Failed to remove Datadog RUM configuration from '$SiteName$AppPath': $_"
            }
        }
        else {
            Write-Verbose "No Datadog RUM configuration found for '$SiteName$AppPath'"
        }

        if ($AppPath -eq "") {
            $childApps = Get-WebApplication -Site $SiteName -ErrorAction SilentlyContinue
        } 
        else {
            $allApps = Get-WebApplication -Site $SiteName -ErrorAction SilentlyContinue
            $childApps = $allApps | Where-Object { $_.Path -like "$AppPath/*" -and $_.Path -ne $AppPath }
        }
        
        foreach ($childApp in $childApps) {
            $childPath = if ($AppPath -eq "") { $childApp.Path } else { "$AppPath$($childApp.Path.Substring($AppPath.Length))" }
            Remove-DatadogRumFromApp -SiteName $SiteName -AppPath $childPath
        }
    }

    $sectionPath = "system.webServer/datadogRum"

    $sites = Get-ChildItem IIS:\Sites
    
    foreach ($site in $sites) {
        Remove-DatadogRumFromApp -SiteName $site.Name -AppPath ""
    }
}
