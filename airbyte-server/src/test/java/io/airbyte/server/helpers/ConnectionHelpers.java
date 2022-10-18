/*
 * Copyright (c) 2022 Airbyte, Inc., all rights reserved.
 */

package io.airbyte.server.helpers;

import com.fasterxml.jackson.databind.JsonNode;
import com.google.common.collect.Lists;
import io.airbyte.api.model.generated.AirbyteCatalog;
import io.airbyte.api.model.generated.AirbyteStream;
import io.airbyte.api.model.generated.AirbyteStreamAndConfiguration;
import io.airbyte.api.model.generated.AirbyteStreamConfiguration;
import io.airbyte.api.model.generated.ConnectionRead;
import io.airbyte.api.model.generated.ConnectionSchedule;
import io.airbyte.api.model.generated.ConnectionSchedule.TimeUnitEnum;
import io.airbyte.api.model.generated.ConnectionScheduleData;
import io.airbyte.api.model.generated.ConnectionScheduleDataBasicSchedule;
import io.airbyte.api.model.generated.ConnectionScheduleType;
import io.airbyte.api.model.generated.ConnectionStatus;
import io.airbyte.api.model.generated.DestinationRead;
import io.airbyte.api.model.generated.JobStatus;
import io.airbyte.api.model.generated.ResourceRequirements;
import io.airbyte.api.model.generated.SourceRead;
import io.airbyte.api.model.generated.SyncMode;
import io.airbyte.api.model.generated.WebBackendConnectionListItem;
import io.airbyte.commons.text.Names;
import io.airbyte.config.BasicSchedule;
import io.airbyte.config.JobSyncConfig.NamespaceDefinitionType;
import io.airbyte.config.Schedule;
import io.airbyte.config.Schedule.TimeUnit;
import io.airbyte.config.ScheduleData;
import io.airbyte.config.StandardSync;
import io.airbyte.protocol.models.CatalogHelpers;
import io.airbyte.protocol.models.ConfiguredAirbyteCatalog;
import io.airbyte.protocol.models.ConfiguredAirbyteStream;
import io.airbyte.protocol.models.DestinationSyncMode;
import io.airbyte.protocol.models.Field;
import io.airbyte.protocol.models.JsonSchemaType;
import io.airbyte.protocol.models.StreamDescriptor;
import io.airbyte.server.converters.ApiPojoConverters;
import io.airbyte.server.handlers.helpers.CatalogConverter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

public class ConnectionHelpers {

  private static final String STREAM_NAME_BASE = "users-data";
  private static final String STREAM_NAME = STREAM_NAME_BASE + "0";
  private static final String FIELD_NAME = "id";
  private static final String BASIC_SCHEDULE_TIME_UNIT = "days";
  private static final long BASIC_SCHEDULE_UNITS = 1L;
  private static final String BASIC_SCHEDULE_DATA_TIME_UNITS = "days";
  private static final long BASIC_SCHEDULE_DATA_UNITS = 1L;
  private static final String ONE_HUNDRED_G = "100g";

  public static final StreamDescriptor STREAM_DESCRIPTOR = new StreamDescriptor().withName(STREAM_NAME);

  // only intended for unit tests, so intentionally set very high to ensure they aren't being used
  // elsewhere
  public static final io.airbyte.config.ResourceRequirements TESTING_RESOURCE_REQUIREMENTS = new io.airbyte.config.ResourceRequirements()
      .withCpuLimit(ONE_HUNDRED_G)
      .withCpuRequest(ONE_HUNDRED_G)
      .withMemoryLimit(ONE_HUNDRED_G)
      .withMemoryRequest(ONE_HUNDRED_G);

  public static StandardSync generateSyncWithSourceId(final UUID sourceId) {
    final UUID connectionId = UUID.randomUUID();

    return new StandardSync()
        .withConnectionId(connectionId)
        .withName("presto to hudi")
        .withNamespaceDefinition(NamespaceDefinitionType.SOURCE)
        .withNamespaceFormat(null)
        .withPrefix("presto_to_hudi")
        .withStatus(StandardSync.Status.ACTIVE)
        .withCatalog(generateBasicConfiguredAirbyteCatalog())
        .withSourceId(sourceId)
        .withDestinationId(UUID.randomUUID())
        .withOperationIds(List.of(UUID.randomUUID()))
        .withManual(false)
        .withSchedule(generateBasicSchedule())
        .withResourceRequirements(TESTING_RESOURCE_REQUIREMENTS);
  }

  public static StandardSync generateSyncWithDestinationId(final UUID destinationId) {
    final UUID connectionId = UUID.randomUUID();

    return new StandardSync()
        .withConnectionId(connectionId)
        .withName("presto to hudi")
        .withNamespaceDefinition(NamespaceDefinitionType.SOURCE)
        .withNamespaceFormat(null)
        .withPrefix("presto_to_hudi")
        .withStatus(StandardSync.Status.ACTIVE)
        .withCatalog(generateBasicConfiguredAirbyteCatalog())
        .withSourceId(UUID.randomUUID())
        .withDestinationId(destinationId)
        .withOperationIds(List.of(UUID.randomUUID()))
        .withManual(true);
  }

  public static ConnectionSchedule generateBasicConnectionSchedule() {
    return new ConnectionSchedule()
        .timeUnit(ConnectionSchedule.TimeUnitEnum.fromValue(BASIC_SCHEDULE_TIME_UNIT))
        .units(BASIC_SCHEDULE_UNITS);
  }

  public static Schedule generateBasicSchedule() {
    return new Schedule()
        .withTimeUnit(TimeUnit.fromValue(BASIC_SCHEDULE_TIME_UNIT))
        .withUnits(BASIC_SCHEDULE_UNITS);
  }

  public static ConnectionScheduleData generateBasicConnectionScheduleData() {
    return new ConnectionScheduleData().basicSchedule(
        new ConnectionScheduleDataBasicSchedule().timeUnit(ConnectionScheduleDataBasicSchedule.TimeUnitEnum.DAYS).units(BASIC_SCHEDULE_UNITS));
  }

  public static ScheduleData generateBasicScheduleData() {
    return new ScheduleData().withBasicSchedule(new BasicSchedule()
        .withTimeUnit(BasicSchedule.TimeUnit.fromValue((BASIC_SCHEDULE_DATA_TIME_UNITS)))
        .withUnits(BASIC_SCHEDULE_DATA_UNITS));
  }

  public static ConnectionRead generateExpectedConnectionRead(final UUID connectionId,
                                                              final UUID sourceId,
                                                              final UUID destinationId,
                                                              final List<UUID> operationIds,
                                                              final UUID sourceCatalogId) {

    return new ConnectionRead()
        .connectionId(connectionId)
        .sourceId(sourceId)
        .destinationId(destinationId)
        .operationIds(operationIds)
        .name("presto to hudi")
        .namespaceDefinition(io.airbyte.api.model.generated.NamespaceDefinitionType.SOURCE)
        .namespaceFormat(null)
        .prefix("presto_to_hudi")
        .status(ConnectionStatus.ACTIVE)
        .schedule(generateBasicConnectionSchedule())
        .scheduleType(ConnectionScheduleType.BASIC)
        .scheduleData(generateBasicConnectionScheduleData())
        .syncCatalog(ConnectionHelpers.generateBasicApiCatalog())
        .resourceRequirements(new ResourceRequirements()
            .cpuRequest(TESTING_RESOURCE_REQUIREMENTS.getCpuRequest())
            .cpuLimit(TESTING_RESOURCE_REQUIREMENTS.getCpuLimit())
            .memoryRequest(TESTING_RESOURCE_REQUIREMENTS.getMemoryRequest())
            .memoryLimit(TESTING_RESOURCE_REQUIREMENTS.getMemoryLimit()))
        .sourceCatalogId(sourceCatalogId);
  }

  public static ConnectionRead generateExpectedConnectionRead(final StandardSync standardSync) {
    final ConnectionRead connectionRead = generateExpectedConnectionRead(
        standardSync.getConnectionId(),
        standardSync.getSourceId(),
        standardSync.getDestinationId(),
        standardSync.getOperationIds(),
        standardSync.getSourceCatalogId());

    if (standardSync.getSchedule() == null) {
      connectionRead.schedule(null);
    } else {
      connectionRead.schedule(new ConnectionSchedule()
          .timeUnit(TimeUnitEnum.fromValue(standardSync.getSchedule().getTimeUnit().value()))
          .units(standardSync.getSchedule().getUnits()));
    }

    return connectionRead;
  }

  public static ConnectionRead connectionReadFromStandardSync(final StandardSync standardSync) {
    final ConnectionRead connectionRead = new ConnectionRead();
    connectionRead
        .connectionId(standardSync.getConnectionId())
        .sourceId(standardSync.getSourceId())
        .destinationId(standardSync.getDestinationId())
        .operationIds(standardSync.getOperationIds())
        .name(standardSync.getName())
        .namespaceFormat(standardSync.getNamespaceFormat())
        .prefix(standardSync.getPrefix())
        .sourceCatalogId(standardSync.getSourceCatalogId());

    if (standardSync.getNamespaceDefinition() != null) {
      connectionRead
          .namespaceDefinition(io.airbyte.api.model.generated.NamespaceDefinitionType.fromValue(standardSync.getNamespaceDefinition().value()));
    }
    if (standardSync.getStatus() != null) {
      connectionRead.status(io.airbyte.api.model.generated.ConnectionStatus.fromValue(standardSync.getStatus().value()));
    }
    ApiPojoConverters.populateConnectionReadSchedule(standardSync, connectionRead);

    if (standardSync.getCatalog() != null) {
      connectionRead.syncCatalog(CatalogConverter.toApi(standardSync.getCatalog()));
    }
    if (standardSync.getResourceRequirements() != null) {
      connectionRead.resourceRequirements(new io.airbyte.api.model.generated.ResourceRequirements()
          .cpuLimit(standardSync.getResourceRequirements().getCpuLimit())
          .cpuRequest(standardSync.getResourceRequirements().getCpuRequest())
          .memoryLimit(standardSync.getResourceRequirements().getMemoryLimit())
          .memoryRequest(standardSync.getResourceRequirements().getMemoryRequest()));
    }
    return connectionRead;
  }

  public static WebBackendConnectionListItem generateExpectedWebBackendConnectionListItem(
                                                                                          final StandardSync standardSync,
                                                                                          final SourceRead source,
                                                                                          final DestinationRead destination,
                                                                                          final boolean isSyncing,
                                                                                          final Long latestSyncJobCreatedAt,
                                                                                          final JobStatus latestSynJobStatus) {

    final WebBackendConnectionListItem connectionListItem = new WebBackendConnectionListItem()
        .connectionId(standardSync.getConnectionId())
        .name(standardSync.getName())
        .sourceId(standardSync.getSourceId())
        .destinationId(standardSync.getDestinationId())
        .source(source)
        .destination(destination)
        .status(ApiPojoConverters.toApiStatus(standardSync.getStatus()))
        .isSyncing(isSyncing)
        .latestSyncJobCreatedAt(latestSyncJobCreatedAt)
        .latestSyncJobStatus(latestSynJobStatus)
        .scheduleType(ApiPojoConverters.toApiConnectionScheduleType(standardSync))
        .scheduleData(ApiPojoConverters.toApiConnectionScheduleData(standardSync));

    return connectionListItem;
  }

  public static JsonNode generateBasicJsonSchema() {
    return CatalogHelpers.fieldsToJsonSchema(Field.of(FIELD_NAME, JsonSchemaType.STRING));
  }

  public static ConfiguredAirbyteCatalog generateBasicConfiguredAirbyteCatalog() {
    return new ConfiguredAirbyteCatalog().withStreams(Collections.singletonList(generateBasicConfiguredStream(null)));
  }

  public static ConfiguredAirbyteCatalog generateMultipleStreamsConfiguredAirbyteCatalog(final int streamsCount) {
    final List<ConfiguredAirbyteStream> configuredStreams = new ArrayList<>();
    for (int i = 0; i < streamsCount; i++) {
      configuredStreams.add(generateBasicConfiguredStream(String.valueOf(i)));
    }
    return new ConfiguredAirbyteCatalog().withStreams(configuredStreams);
  }

  public static ConfiguredAirbyteStream generateBasicConfiguredStream(final String nameSuffix) {
    return new ConfiguredAirbyteStream()
        .withStream(generateBasicAirbyteStream(nameSuffix))
        .withCursorField(Lists.newArrayList(FIELD_NAME))
        .withSyncMode(io.airbyte.protocol.models.SyncMode.INCREMENTAL)
        .withDestinationSyncMode(DestinationSyncMode.APPEND);
  }

  private static io.airbyte.protocol.models.AirbyteStream generateBasicAirbyteStream(final String nameSuffix) {
    return CatalogHelpers.createAirbyteStream(
        nameSuffix == null ? STREAM_NAME : STREAM_NAME_BASE + nameSuffix, Field.of(FIELD_NAME, JsonSchemaType.STRING))
        .withDefaultCursorField(Lists.newArrayList(FIELD_NAME))
        .withSourceDefinedCursor(false)
        .withSupportedSyncModes(List.of(io.airbyte.protocol.models.SyncMode.FULL_REFRESH, io.airbyte.protocol.models.SyncMode.INCREMENTAL));
  }

  public static AirbyteCatalog generateBasicApiCatalog() {
    return new AirbyteCatalog().streams(Lists.newArrayList(new AirbyteStreamAndConfiguration()
        .stream(generateBasicApiStream(null))
        .config(generateBasicApiStreamConfig(null))));
  }

  public static AirbyteCatalog generateMultipleStreamsApiCatalog(final int streamsCount) {
    final List<AirbyteStreamAndConfiguration> streamAndConfigurations = new ArrayList<>();
    for (int i = 0; i < streamsCount; i++) {
      streamAndConfigurations.add(new AirbyteStreamAndConfiguration()
          .stream(generateBasicApiStream(String.valueOf(i)))
          .config(generateBasicApiStreamConfig(String.valueOf(i))));
    }
    return new AirbyteCatalog().streams(streamAndConfigurations);
  }

  private static AirbyteStreamConfiguration generateBasicApiStreamConfig(final String nameSuffix) {
    return new AirbyteStreamConfiguration()
        .syncMode(SyncMode.INCREMENTAL)
        .cursorField(Lists.newArrayList(FIELD_NAME))
        .destinationSyncMode(io.airbyte.api.model.generated.DestinationSyncMode.APPEND)
        .primaryKey(Collections.emptyList())
        .aliasName(Names.toAlphanumericAndUnderscore(nameSuffix == null ? STREAM_NAME : STREAM_NAME_BASE + nameSuffix))
        .selected(true);
  }

  private static AirbyteStream generateBasicApiStream(final String nameSuffix) {
    return new AirbyteStream()
        .name(nameSuffix == null ? STREAM_NAME : STREAM_NAME_BASE + nameSuffix)
        .jsonSchema(generateBasicJsonSchema())
        .defaultCursorField(Lists.newArrayList(FIELD_NAME))
        .sourceDefinedCursor(false)
        .sourceDefinedPrimaryKey(Collections.emptyList())
        .supportedSyncModes(List.of(SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL));
  }

}