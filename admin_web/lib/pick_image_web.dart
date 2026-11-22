import 'dart:async';
import 'dart:js_interop';

import 'package:web/web.dart' as web;

/// Opens the browser's file picker for one PNG/JPEG picture; returns it as a data URL, or null if cancelled.
Future<String?> pickImageDataUrl() {
  final done = Completer<String?>();
  final input = web.HTMLInputElement()
    ..type = 'file'
    ..accept = 'image/png,image/jpeg';
  input.onchange = ((web.Event _) {
    final file = input.files?.item(0);
    if (file == null) {
      done.complete(null);
      return;
    }
    final reader = web.FileReader();
    reader.onload = ((web.Event _) => done.complete((reader.result as JSString?)?.toDart)).toJS;
    reader.onerror = ((web.Event _) => done.complete(null)).toJS;
    reader.readAsDataURL(file);
  }).toJS;
  input.click();
  return done.future;
}
