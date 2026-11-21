// Android app module build: package name, SDK versions (min Android 8.0), Java/Kotlin 17, Firebase, signing.

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Firebase config (google-services.json from the Firebase console). Applied only when the file is
// present, so the app still builds without it (Google sign-in is then unavailable; dev sign-in works).
if (file("google-services.json").exists()) {
    apply(plugin = "com.google.gms.google-services")
}

android {
    namespace = "com.checkscam.checkscam"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // Must match the Android package name registered in Firebase (google-services.json).
        // The Kotlin code keeps its own package (namespace above); only this ID is seen by Android/Firebase.
        applicationId = "com.check.check"
        minSdk = 26 // Android 8.0 (notification channels)
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode // from pubspec.yaml "version: x.y.z+code"
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            // Signed with the debug key for now (Phase 11 adds a real release key).
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

dependencies {
    // Lets the Kotlin SMS listener get a fresh Firebase ID token by itself (tokens expire after 1 hour).
    // BoM version matches the one used by the firebase_core Flutter plugin.
    implementation(platform("com.google.firebase:firebase-bom:35.2.0"))
    implementation("com.google.firebase:firebase-auth")
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
