import Croppie from 'croppie'
import 'croppie/croppie.css'
import { nextTick } from 'vue'

export function useImageCropper(options = {}) {
  const {
    viewportWidth = 200,
    viewportHeight = 200,
    viewportType = 'square',
    boundaryWidth = 300,
    boundaryHeight = 300,
  } = options

  let croppie = null

  function init(el, photoUrl) {
    if (!croppie) {
      croppie = new Croppie(el, {
        viewport: { width: viewportWidth, height: viewportHeight, type: viewportType },
        boundary: { width: boundaryWidth, height: boundaryHeight },
        enableOrientation: true,
        enforceBoundary: true,
      })
    }
    croppie.bind({ url: photoUrl })
  }

  async function crop() {
    if (!croppie) return null
    return croppie.result({ type: 'base64', size: 'viewport' })
  }

  function destroy() {
    croppie?.destroy()
    croppie = null
  }

  return { init, crop, destroy }
}
