# Add project specific ProGuard rules here.
# Keep Retrofit and Serialization models
-keepattributes *Annotation*
-keepclassmembers,allowobfuscation class * {
    @kotlinx.serialization.SerialName <fields>;
}
-keep,includedescriptorclasses class com.calleroo.app.**$$serializer { *; }
-keepclassmembers class com.calleroo.app.** {
    *** Companion;
}
-keepclasseswithmembers class com.calleroo.app.** {
    kotlinx.serialization.KSerializer serializer(...);
}
