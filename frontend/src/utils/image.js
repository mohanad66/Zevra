// Client-side image compression before upload.
//
// Goal: keep every user-uploaded image under 330 KB so multipart uploads are
// fast and the server stores little. The source is decoded to an off-screen
// canvas, capped at a sane long edge, and re-encoded as JPEG ("white" fill
// replaces any alpha channel). Large files are shrunk by lowering the JPEG
// quality first, then the dimensions, until the size budget is met. Anything
// that cannot be decoded (HEIC, corrupt files, ...) passes through unchanged
// and the backend still accepts it.

const DEFAULT_MAX_BYTES = 330 * 1024
const DEFAULT_MAX_DIM = 1600
const DEFAULT_MIN_DIM = 720
const DEFAULT_START_QUALITY = 0.82
const DEFAULT_MIN_QUALITY = 0.42
const QUALITY_STEP = 0.1
const DIM_STEP = 0.85

function loadBitmap(file) {
  if (typeof createImageBitmap === 'function') {
    return createImageBitmap(file, { imageOrientation: 'from-image' })
      .catch(() => loadViaImage(file))
  }
  return loadViaImage(file)
}

function loadViaImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => { URL.revokeObjectURL(url); resolve(img) }
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Unable to decode image')) }
    img.src = url
  })
}

function canvasToBlob(canvas, quality) {
  return new Promise((resolve) => canvas.toBlob((b) => resolve(b), 'image/jpeg', quality))
}

async function encode(bitmap, width, height, quality) {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d', { alpha: false })
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, width, height)
  ctx.drawImage(bitmap, 0, 0, width, height)
  return canvasToBlob(canvas, quality)
}

function jpgName(name) {
  const base = (name || 'image').replace(/\.[^.]+$/, '')
  return `${base}.jpg`
}

/**
 * Return a compressed copy of `file` whose encoded size is at most `maxBytes`.
 * Falls back to the original file when compression is not possible or would
 * not help.
 */
export async function compressImage(file, opts = {}) {
  const {
    maxBytes = DEFAULT_MAX_BYTES,
    maxDim = DEFAULT_MAX_DIM,
    minDim = DEFAULT_MIN_DIM,
    startQuality = DEFAULT_START_QUALITY,
    minQuality = DEFAULT_MIN_QUALITY,
  } = opts

  if (!file || typeof file.type !== 'string' || !file.type.startsWith('image/')) return file
  // Already within the size budget: no need to re-encode.
  if (file.size && file.size <= maxBytes) return file

  let bitmap
  try {
    bitmap = await loadBitmap(file)
  } catch {
    return file
  }

  try {
    let width = bitmap.width || bitmap.naturalWidth
    let height = bitmap.height || bitmap.naturalHeight
    if (!width || !height) return file

    if (Math.max(width, height) > maxDim) {
      const scale = maxDim / Math.max(width, height)
      width = Math.round(width * scale)
      height = Math.round(height * scale)
    }

    let quality = startQuality
    let blob = await encode(bitmap, width, height, quality)
    while (blob && blob.size > maxBytes && quality > minQuality) {
      quality = Math.max(minQuality, quality - QUALITY_STEP)
      blob = await encode(bitmap, width, height, quality)
    }
    while (blob && blob.size > maxBytes && Math.max(width, height) > minDim) {
      const longest = Math.max(width, height)
      const factor = Math.max(minDim / longest, DIM_STEP)
      width = Math.max(1, Math.round(width * factor))
      height = Math.max(1, Math.round(height * factor))
      blob = await encode(bitmap, width, height, quality)
    }

    if (!blob || blob.size >= file.size) return file
    return new File([blob], jpgName(file.name), { type: 'image/jpeg', lastModified: Date.now() })
  } finally {
    if (bitmap.close) bitmap.close()
  }
}