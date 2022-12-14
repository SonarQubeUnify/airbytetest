/*
 * Copyright (c) 2022 Airbyte, Inc., all rights reserved.
 */

package io.airbyte.commons.protocol.serde;

import io.airbyte.commons.version.AirbyteVersion;

public interface AirbyteMessageDeserializer<T> {

  T deserialize(final String json);

  AirbyteVersion getTargetVersion();

}
