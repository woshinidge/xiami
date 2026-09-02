#pragma once

#include <array>

namespace xiami::mir_palette {

using Color = std::array<unsigned char, 4>;
const std::array<Color, 256>& rgba();

}  // namespace xiami::mir_palette
