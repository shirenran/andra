plugins { id("com.android.application") }

android {
    namespace = "dev.andra.runtime"
    compileSdk = 36

    defaultConfig {
        applicationId = "dev.andra.runtime"
        minSdk = 28
        targetSdk = 36
        versionCode = 19
        versionName = "1.2.7"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    compileOnly("de.robv.android.xposed:api:82")
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
