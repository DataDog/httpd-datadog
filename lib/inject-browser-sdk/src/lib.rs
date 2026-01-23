#![no_std]
#![allow(deprecated)] // allow internal usage of deprecated things

extern crate alloc;
#[cfg(any(feature = "std", test))]
extern crate std;

// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache 2.0 License. This product includes software developed at
// Datadog (https://www.datadoghq.com/).
//
// Copyright 2024-Present Datadog, Inc.

mod configuration;
pub mod error;
mod injection_point_locator;
pub mod injector;
mod snippet;

pub use configuration::*;
pub use snippet::*;
