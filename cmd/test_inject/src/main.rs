use std::{env, fs, io::Write as _, process};

use inject_browser_sdk::{
    generate_snippet,
    injector::{Injector, Result as InjectorResult},
    Configuration, RumConfiguration,
};

fn main() {
    let Some(input_file_path) = env::args().nth(1) else {
        println!("Usage: {} <input_file>", env::args().nth(0).unwrap());
        process::exit(1);
    };

    let input_file_content = match fs::read(&input_file_path) {
        Ok(content) => content,
        Err(err) => {
            println!("Error reading file {}: {}", input_file_path, err);
            process::exit(1);
        }
    };

    let configuration = Configuration {
        major_version: 6,
        rum: RumConfiguration {
            application_id: Box::from("xxx"),
            client_token: Box::from("xxx"),
            ..Default::default()
        },
    };

    let snippet = match generate_snippet(&configuration) {
        Ok(snippet) => snippet,
        Err(err) => {
            println!("Error generating snippet: {}", err);
            process::exit(1);
        }
    };

    let mut injector = Injector::new(&snippet);
    print_injector_result(injector.write(&input_file_content));
    print_injector_result(injector.end());
}

fn print_injector_result(result: InjectorResult) {
    for slice in result.slices[..result.length].iter() {
        std::io::stdout().write_all(slice.bytes).unwrap();
    }
}
