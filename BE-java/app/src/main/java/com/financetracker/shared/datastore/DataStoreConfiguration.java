package com.financetracker.shared.datastore;

import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;

import com.financetracker.shared.config.DataStoreType;

@Configuration(proxyBeanMethods = false)
class DataStoreConfiguration {

    /** Lets app.datastore accept the Django spellings (sqlite/firestore) as well as jpa. */
    @Bean
    @ConfigurationPropertiesBinding
    static Converter<String, DataStoreType> dataStoreTypeConverter() {
        return DataStoreType::parse;
    }
}
