// Picks a PNG/JPEG picture in the browser and returns it as a data URL ("data:image/png;base64,...") - for ads (A9).
// The browser version uses package:web; tests (not in a browser) get a version that returns null.
export 'pick_image_stub.dart' if (dart.library.js_interop) 'pick_image_web.dart';
