import streamlit as st
import mysql.connector
import decimal
import pandas as pd
import datetime
from datetime import timedelta, time
from itertools import combinations
from google.oauth2 import service_account
import gspread 
import webbrowser
import re

def gerar_df_phoenix(vw_name):
    # Parametros de Login AWS
    config = {
    'user': 'user_automation_jpa',
    'password': 'luck_jpa_2024',
    'host': 'comeia.cixat7j68g0n.us-east-1.rds.amazonaws.com',
    'database': 'test_phoenix_maceio'
    }
    # Conexão as Views
    conexao = mysql.connector.connect(**config)
    cursor = conexao.cursor()

    request_name = f'SELECT * FROM {vw_name}'

    # Script MySql para requests
    cursor.execute(
        request_name
    )
    # Coloca o request em uma variavel
    resultado = cursor.fetchall()
    # Busca apenas o cabecalhos do Banco
    cabecalho = [desc[0] for desc in cursor.description]

    # Fecha a conexão
    cursor.close()
    conexao.close()

    # Coloca em um dataframe e muda o tipo de decimal para float
    df = pd.DataFrame(resultado, columns=cabecalho)
    df = df.applymap(lambda x: float(x) if isinstance(x, decimal.Decimal) else x)
    return df

def puxar_sequencias_hoteis():

    nome_credencial = st.secrets["CREDENCIAL_SHEETS"]
    credentials = service_account.Credentials.from_service_account_info(nome_credencial)
    scope = ['https://www.googleapis.com/auth/spreadsheets']
    credentials = credentials.with_scopes(scope)
    client = gspread.authorize(credentials)

    # Abrir a planilha desejada pelo seu ID
    spreadsheet = client.open_by_key('1ebhHZGC60jawQqnjnF9V7Jr5DEsRsSeZE60Oxg4KA7g')

    lista_abas = ['Hoteis Orla Maceio', 'Hoteis Grande Maceio', 'Hoteis Maragogi', 'Hoteis Santo Antonio', 'Hoteis Frances', 
                  'Hoteis Milagres', 'Hoteis Sao Miguel', 'Hoteis Porto']

    lista_df_hoteis = ['df_hoteis_orla_maceio', 'df_hoteis_grande_maceio', 'df_hoteis_maragogi', 'df_hoteis_santo_antonio', 
                       'df_hoteis_frances', 'df_hoteis_milagres', 'df_hoteis_sao_miguel', 'df_hoteis_porto']

    for index in range(len(lista_abas)):

        aba = lista_abas[index]

        df_hotel = lista_df_hoteis[index]
        
        sheet = spreadsheet.worksheet(aba)

        sheet_data = sheet.get_all_values()

        st.session_state[df_hotel] = pd.DataFrame(sheet_data[1:], columns=sheet_data[0])

def transformar_timedelta(intervalo):
    
    intervalo = timedelta(hours=intervalo.hour, minutes=intervalo.minute, seconds=intervalo.second)

    return intervalo

def objeto_intervalo(titulo, valor_padrao, chave):

    intervalo_ref = st.time_input(label=titulo, value=valor_padrao, key=chave, step=300)
    
    intervalo_ref = transformar_timedelta(intervalo_ref)

    return intervalo_ref

def gerar_itens_faltantes(df_servicos, df_hoteis):

    lista_hoteis_df_router = df_servicos['Est Origem'].unique().tolist()

    lista_hoteis_sequencia = df_hoteis['Est Origem'].unique().tolist()

    itens_faltantes = set(lista_hoteis_df_router) - set(lista_hoteis_sequencia)

    itens_faltantes = list(itens_faltantes)

    return itens_faltantes, lista_hoteis_df_router

def inserir_hoteis_faltantes(itens_faltantes, df_hoteis, aba_excel, regiao):

    df_itens_faltantes = pd.DataFrame(itens_faltantes, columns=['Est Origem'])

    st.dataframe(df_itens_faltantes, hide_index=True)

    df_itens_faltantes[['Região', 'Sequência', 'Bus', 'Micro', 'Van']]=''

    df_hoteis_geral = pd.concat([df_hoteis, df_itens_faltantes])

    nome_credencial = st.secrets["CREDENCIAL_SHEETS"]
    credentials = service_account.Credentials.from_service_account_info(nome_credencial)
    scope = ['https://www.googleapis.com/auth/spreadsheets']
    credentials = credentials.with_scopes(scope)
    client = gspread.authorize(credentials)
    
    spreadsheet = client.open_by_key('1ebhHZGC60jawQqnjnF9V7Jr5DEsRsSeZE60Oxg4KA7g')

    sheet = spreadsheet.worksheet(aba_excel)
    sheet_data = sheet.get_all_values()
    limpar_colunas = "A:F"
    sheet.batch_clear([limpar_colunas])
    data = [df_hoteis_geral.columns.values.tolist()] + df_hoteis_geral.values.tolist()
    sheet.update("A1", data)

    st.error('Os hoteis acima não estão cadastrados na lista de sequência de hoteis.' + 
             f' Eles foram inseridos no final da lista de {regiao}. Por favor, coloque-os na sequência e tente novamente')


def ordenar_juncoes(df_router_ref):

    max_juncao = df_router_ref['Junção'].dropna().max()

    if pd.isna(max_juncao):

        max_juncao = 0

    for juncao in range(1, int(max_juncao) + 1):

        df_ref = df_router_ref[(df_router_ref['Modo do Servico']=='REGULAR') & (df_router_ref['Junção']==juncao)]\
            .sort_values(by='Sequência', ascending=False).reset_index()

        if len(df_ref)>0:

            index_inicial = df_ref['index'].min()
    
            index_final = df_ref['index'].max()
    
            df_ref = df_ref.drop('index', axis=1)
    
            df_router_ref.iloc[index_inicial:index_final+1] = df_ref

    return df_router_ref

def colocar_menor_horario_juncao(df_router_ref, df_juncao_voos):

    df_menor_horario = pd.DataFrame(columns=['Junção', 'Menor Horário'])

    contador=0

    for juncao in df_juncao_voos['Junção'].unique().tolist():

        menor_horario = df_juncao_voos[df_juncao_voos['Junção']==juncao]['Horário'].min()

        df_menor_horario.at[contador, 'Junção']=juncao

        df_menor_horario.at[contador, 'Menor Horário']=menor_horario

        contador+=1

    df_router_ref = pd.merge(df_router_ref, df_menor_horario, on='Junção', how='left')

    return df_router_ref

def criar_df_servicos_2(df_servicos, df_juncao_voos, df_hoteis):

    # Criando coluna de paxs totais

    df_servicos['Total ADT | CHD'] = df_servicos['Total ADT'] + df_servicos['Total CHD']    

    # Preenchendo coluna 'Data Horario Apresentacao'

    df_servicos['Data Horario Apresentacao'] = pd.to_datetime(df_servicos['Data Voo'] + ' ' + df_servicos['Horario Voo'])
    
    # Criando coluna de Junção através de pd.merge

    df_servicos_2 = pd.merge(df_servicos, df_juncao_voos[['Servico', 'Voo', 'Junção']], on=['Servico', 'Voo'], how='left')

    # Criando colunas Micro Região e Sequência através de pd.merge

    df_servicos_2 = pd.merge(df_servicos_2, df_hoteis, on='Est Origem', how='left')

    # Ordenando dataframe por ['Modo do Servico', 'Servico', 'Junção', 'Voo', 'Sequência']

    df_servicos_2 = df_servicos_2.sort_values(by=['Modo do Servico', 'Junção', 'Voo', 'Sequência'], 
                                              ascending=[True, True, True, False]).reset_index(drop=True)

    # Ordenando cada junção pela sequência de hoteis

    df_servicos_2 = ordenar_juncoes(df_servicos_2)

    # Colocando qual o menor horário de cada junção

    df_servicos_2 = colocar_menor_horario_juncao(df_servicos_2, df_juncao_voos)

    # Criando colunas Roteiro e Carros

    df_servicos_2['Roteiro']=0

    df_servicos_2['Carros']=0

    return df_servicos_2

def definir_horario_primeiro_hotel(df, index, intervalo_inicial_orla_maceio, intervalo_inicial_grande_maceio, 
                                   intervalo_inicial_maragogi, intervalo_inicial_santo_antonio, intervalo_inicial_porto):

    servico = df.at[index, 'Servico']

    data_voo = df.at[index, 'Data Voo']

    nome_voo = df.at[index, 'Voo']

    if 'Junção' in df.columns.tolist():

        juncao = df.at[index, 'Junção']

    else:

        juncao = None

    modo = df.at[index, 'Modo do Servico']

    if pd.isna(juncao) or modo!='REGULAR':

        hora_voo = df.at[index, 'Horario Voo']

    else:

        hora_voo = df.at[index, 'Menor Horário']

    data_hora_voo_str = f'{data_voo} {hora_voo}'

    data_hora_voo = pd.to_datetime(data_hora_voo_str, format='%Y-%m-%d %H:%M:%S')

    if servico=='OUT - ORLA DE MACEIÓ (OU PRÓXIMOS) ':

        if time(0, 0, 0) <= hora_voo <= time(5, 0, 0):

            intervalo_inicial_orla_maceio -= timedelta(minutes=30)
        
        return data_hora_voo - intervalo_inicial_orla_maceio
    
    elif servico=='OUT - GRANDE MACEIÓ' or servico=='OUT - BARRA DE SÃO MIGUEL' or 'OUT- FRANCÊS':

        if servico=='OUT - GRANDE MACEIÓ' and (nome_voo in voos_fret):

            intervalo_inicial_grande_maceio = timedelta(hours=3, minutes=0, seconds=0)

        elif time(0, 0, 0) <= hora_voo <= time(5, 0, 0):

            intervalo_inicial_grande_maceio -= timedelta(minutes=30)

        return data_hora_voo - intervalo_inicial_grande_maceio
    
    elif servico=='OUT - MARAGOGI / JAPARATINGA' or servico=='OUT - SÃO MIGUEL DOS MILAGRES ':

        if time(0, 0, 0) <= hora_voo <= time(5, 0, 0):

            intervalo_inicial_maragogi -= timedelta(minutes=30)

        return data_hora_voo - intervalo_inicial_maragogi
    
    elif servico=='OUT - BARRA DE SANTO ANTÔNIO':

        if time(0, 0, 0) <= hora_voo <= time(5, 0, 0):

            intervalo_inicial_santo_antonio -= timedelta(minutes=30)

        return data_hora_voo - intervalo_inicial_santo_antonio
    
    elif servico=='OUT - PORTO DE GALINHAS':

        if time(0, 0, 0) <= hora_voo <= time(5, 0, 0):

            intervalo_inicial_porto -= timedelta(minutes=30)

        return data_hora_voo - intervalo_inicial_porto

def roteirizar_fretamentos(df_fretamentos, roteiro):

    for escala in df_fretamentos['Escala'].unique().tolist():

        roteiro+=1

        carros=1

        df_ref = df_fretamentos[df_fretamentos['Escala']==escala].reset_index(drop=True)

        for index_2, value in df_ref['index'].items():

            if value==df_ref['index'].min():

                df_ref.at[index_2, 'Data Horario Apresentacao'] = \
                    definir_horario_primeiro_hotel(df_ref, index_2, intervalo_inicial_orla_maceio, intervalo_inicial_grande_maceio, 
                                                   intervalo_inicial_maragogi, intervalo_inicial_santo_antonio, intervalo_inicial_porto)

                df_ref = preencher_roteiro_carros(df_ref, roteiro, carros, index_2)

            elif df_ref.at[index_2, 'Est Origem']==df_ref.at[index_2-1, 'Est Origem']:

                df_ref.at[index_2, 'Data Horario Apresentacao'] = df_ref.at[index_2-1, 'Data Horario Apresentacao']

                df_ref = preencher_roteiro_carros(df_ref, roteiro, carros, index_2)

            else:

                intervalo_ref = definir_intervalo_ref(df_ref, index_2, intervalo_hoteis_bairros_iguais, 
                                                    intervalo_hoteis_bairros_diferentes, sequencia_ritz)

                df_ref.at[index_2, 'Data Horario Apresentacao'] = df_ref.at[index_2-1, 'Data Horario Apresentacao']-intervalo_ref

                df_ref = preencher_roteiro_carros(df_ref, roteiro, carros, index_2)

            df_fretamentos.loc[df_fretamentos['index']==value, 'Data Horario Apresentacao'] = \
                df_ref.at[index_2, 'Data Horario Apresentacao']
            
            df_fretamentos.loc[df_fretamentos['index']==value, 'Roteiro'] = df_ref.at[index_2, 'Roteiro']
            
            df_fretamentos.loc[df_fretamentos['index']==value, 'Carros'] = df_ref.at[index_2, 'Carros']
            
    df_fretamentos = df_fretamentos.drop(columns=['index'])
            
    return df_fretamentos, roteiro

def roteirizar_hoteis_mais_pax_max(df_servicos, roteiro, df_hoteis_pax_max):

    # Criando dataframes com os hoteis que estouram a capacidade máxima da frota em um mesmo voo

    df_ref_sem_juncao = df_servicos[(df_servicos['Bus']=='X') & (pd.isna(df_servicos['Junção']))]\
        .groupby(['Modo do Servico', 'Servico', 'Voo', 'Est Origem']).agg({'Total ADT | CHD': 'sum'}).reset_index()

    df_ref_sem_juncao = df_ref_sem_juncao[df_ref_sem_juncao['Total ADT | CHD']>=pax_max].reset_index()

    # Criando dataframes com os hoteis que estouram a capacidade máxima da frota em uma mesma junção

    df_ref_com_juncao = df_servicos[(df_servicos['Bus']=='X') & ~(pd.isna(df_servicos['Junção']))]\
        .groupby(['Modo do Servico', 'Servico', 'Junção', 'Est Origem']).agg({'Total ADT | CHD': 'sum'}).reset_index()

    df_ref_com_juncao = df_ref_com_juncao[df_ref_com_juncao['Total ADT | CHD']>=pax_max].reset_index()

    # Se houver hotel em uma mesma junção com mais paxs que a capacidade máxima da frota, vai inserindo o horário de apresentação de cada hotel 
    # e tira de df_router_filtrado_2

    if len(df_ref_com_juncao)>0:

        for index in range(len(df_ref_com_juncao)):

            carro=0

            roteiro+=1

            pax_ref = df_ref_com_juncao.at[index, 'Total ADT | CHD']

            loops = int(pax_ref//pax_max)

            modo = df_ref_com_juncao.at[index, 'Modo do Servico']

            servico = df_ref_com_juncao.at[index, 'Servico']

            ref_juncao = df_ref_com_juncao.at[index, 'Junção']

            hotel = df_ref_com_juncao.at[index, 'Est Origem']

            st.warning(f'O hotel {hotel} da junção {ref_juncao} tem {pax_ref} paxs e, portanto vai ser roteirizado em um ônibus')

            for loop in range(loops):

                carro+=1

                df_hotel_pax_max = df_servicos[(df_servicos['Modo do Servico']==modo) & (df_servicos['Servico']==servico) & 
                                                (df_servicos['Junção']==ref_juncao) & (df_servicos['Est Origem']==hotel)].reset_index()
                
                paxs_total_ref = 0
                
                for index_2, value in df_hotel_pax_max['Total ADT | CHD'].items():

                    if paxs_total_ref+value>pax_max:

                        break

                    else:

                        paxs_total_ref+=value

                        df_servicos = df_servicos.drop(index=df_hotel_pax_max.at[index_2, 'index'])

                        df_hoteis_pax_max = pd.concat([df_hoteis_pax_max, df_hotel_pax_max.loc[[index_2]]])

                        df_hoteis_pax_max.at[index_2, 'Roteiro']=roteiro

                        df_hoteis_pax_max.at[index_2, 'Carros']=carro

    # Se houver hotel em um mesmo voo com mais paxs que a capacidade máxima da frota, vai inserindo o horário de apresentação de cada hotel 
    # e tira de df_router_filtrado_2

    if len(df_ref_sem_juncao)>0:

        for index in range(len(df_ref_sem_juncao)):

            carro=0

            roteiro+=1

            pax_ref = df_ref_sem_juncao.at[index, 'Total ADT | CHD']

            loops = int(pax_ref//pax_max)

            modo = df_ref_sem_juncao.at[index, 'Modo do Servico']

            servico = df_ref_sem_juncao.at[index, 'Servico']

            ref_voo = df_ref_sem_juncao.at[index, 'Voo']

            hotel = df_ref_sem_juncao.at[index, 'Est Origem']

            st.warning(f'O hotel {hotel} do voo {ref_voo} tem {pax_ref} paxs e, portanto vai ser roteirizado em um ônibus')

            for loop in range(loops):

                carro+=1

                df_hotel_pax_max = df_servicos[(df_servicos['Modo do Servico']==modo) & (df_servicos['Servico']==servico) & 
                                                (df_servicos['Voo']==ref_voo) & (df_servicos['Est Origem']==hotel)].reset_index()
                
                paxs_total_ref = 0
                
                for index_2, value in df_hotel_pax_max['Total ADT | CHD'].items():

                    if paxs_total_ref+value>pax_max:

                        break

                    else:

                        paxs_total_ref+=value

                        df_servicos = df_servicos.drop(index=df_hotel_pax_max.at[index_2, 'index'])

                        df_hoteis_pax_max = pd.concat([df_hoteis_pax_max, df_hotel_pax_max.loc[[index_2]]])

                        df_hoteis_pax_max.at[index_2, 'Roteiro']=roteiro

                        df_hoteis_pax_max.at[index_2, 'Carros']=carro

    if len(df_hoteis_pax_max)>0:

        df_hoteis_pax_max['Horario Voo'] = pd.to_datetime(df_hoteis_pax_max['Horario Voo'], format='%H:%M:%S').dt.time
    
        df_hoteis_pax_max['Menor Horário'] = pd.to_datetime(df_hoteis_pax_max['Menor Horário'], format='%H:%M:%S').dt.time

    for index in range(len(df_hoteis_pax_max)):

        df_hoteis_pax_max.at[index, 'Data Horario Apresentacao'] = \
            definir_horario_primeiro_hotel(df_hoteis_pax_max, index, intervalo_inicial_orla_maceio, intervalo_inicial_grande_maceio, 
                                           intervalo_inicial_maragogi, intervalo_inicial_santo_antonio, intervalo_inicial_porto)

    df_servicos = df_servicos.reset_index(drop=True)

    if 'index' in df_hoteis_pax_max.columns.tolist():

        df_hoteis_pax_max = df_hoteis_pax_max.drop(columns=['index'])

    return df_servicos, df_hoteis_pax_max, roteiro

def definir_intervalo_ref(df, value, intervalo_hoteis_bairros_iguais, intervalo_hoteis_bairros_diferentes, sequencia_ritz):

    if (df.at[value-1, 'Sequência']>=sequencia_ritz) & (df.at[value, 'Est Origem']=='FLIX HOTEL'):

        return intervalo_hoteis_bairros_iguais*3

    elif (df.at[value-1, 'Região']=='CRUZ DAS ALMAS') & (df.at[value, 'Região']=='PAJUÇARA'):

        return intervalo_hoteis_bairros_diferentes*2
    
    elif (df.at[value-1, 'Região']=='JATIUCA') & (df.at[value, 'Região']=='PAJUÇARA'):

        return intervalo_hoteis_bairros_iguais*3

    elif df.at[value-1, 'Região']==df.at[value, 'Região']:

        return intervalo_hoteis_bairros_iguais
    
    elif df.at[value-1, 'Região']!=df.at[value, 'Região']:

        return intervalo_hoteis_bairros_diferentes

def verificar_combinacoes(df, max_hoteis, pax_max, df_hoteis, intervalo_hoteis_bairros_iguais, intervalo_hoteis_bairros_diferentes):

    for tamanho in range(2, max_hoteis+1):  # De 2 a 8 hotéis
        
        for i in range(len(df) - tamanho + 1):
            
            # Selecionar a combinação de 'tamanho' hotéis consecutivos
            
            subset = df.iloc[i:i+tamanho]
            
            soma_passageiros = subset['Total ADT | CHD'].sum()

            # Verificar se a soma ultrapassa o valor estipulado

            if soma_passageiros >= int(0.9*pax_max) and soma_passageiros<=pax_max:

                lista_combinacao = list(subset['Est Origem'])

                df_lista_combinacao = pd.DataFrame(lista_combinacao, columns=['Est Origem'])

                df_lista_combinacao = pd.merge(df_lista_combinacao, df_hoteis, on='Est Origem', how='left')

                if len(df_lista_combinacao)>1:

                    intervalo_total = pd.Timedelta(0)

                    for index in range(len(df_lista_combinacao)-1):
    
                        intervalo_ref = definir_intervalo_ref(df_lista_combinacao, index+1, intervalo_hoteis_bairros_iguais, 
                                                              intervalo_hoteis_bairros_diferentes, sequencia_ritz)
                        
                        intervalo_total+=intervalo_ref

                if intervalo_total<=intervalo_pu_hotel:

                    return lista_combinacao

def roteirizar_voo_juncao_mais_pax_max(df_servicos, roteiro, max_hoteis, pax_max, df_hoteis, intervalo_hoteis_bairros_iguais, 
                                       intervalo_hoteis_bairros_diferentes, df_juncoes_pax_max, df_voos_pax_max):
    
    parar_loop=0
    
    if pax_max > 25:

        mask_servicos_com_juncao = (df_servicos['Bus']=='X') & (~pd.isna(df_servicos['Junção'])) & \
            (df_servicos['Modo do Servico']=='REGULAR')
        
        mask_servicos_sem_juncao = (df_servicos['Bus']=='X') & (pd.isna(df_servicos['Junção'])) & \
                            (df_servicos['Modo do Servico']=='REGULAR')
        
    else:

        mask_servicos_com_juncao = (df_servicos['Micro']=='X') & (~pd.isna(df_servicos['Junção'])) & \
            (df_servicos['Modo do Servico']=='REGULAR')
        
        mask_servicos_sem_juncao = (df_servicos['Micro']=='X') & (pd.isna(df_servicos['Junção'])) & \
                            (df_servicos['Modo do Servico']=='REGULAR')

    while True:

        df_hoteis_bus_sem_juncao = df_servicos[mask_servicos_sem_juncao].groupby('Voo').agg({'Total ADT | CHD': 'sum'}).reset_index()
        
        df_hoteis_bus_sem_juncao = df_hoteis_bus_sem_juncao[df_hoteis_bus_sem_juncao['Total ADT | CHD']>=int(0.9*pax_max)].reset_index(drop=True)
        
        df_hoteis_bus_com_juncao = df_servicos[mask_servicos_com_juncao].groupby('Junção').agg({'Total ADT | CHD': 'sum'}).reset_index()

        df_hoteis_bus_com_juncao = df_hoteis_bus_com_juncao[df_hoteis_bus_com_juncao['Total ADT | CHD']>=int(0.9*pax_max)].reset_index(drop=True)

        if len(df_hoteis_bus_com_juncao)>0 or len(df_hoteis_bus_sem_juncao)>0:

            if len(df_hoteis_bus_com_juncao)>0:

                for index in range(len(df_hoteis_bus_com_juncao)):

                    juncao = df_hoteis_bus_com_juncao.at[index, 'Junção']

                    if pax_max > 25:

                        mask_servicos = (df_servicos['Bus']=='X') & (df_servicos['Junção']==juncao) & \
                            (df_servicos['Modo do Servico']=='REGULAR')
                        
                    else:

                        mask_servicos = (df_servicos['Micro']=='X') & (df_servicos['Junção']==juncao) & \
                            (df_servicos['Modo do Servico']=='REGULAR')
                        
                    df_ref = df_servicos[mask_servicos].groupby('Est Origem')\
                                                .agg({'Total ADT | CHD': 'sum', 'Sequência': 'first'})\
                                                    .sort_values(by='Sequência', ascending=False).reset_index()

                    lista_combinacao = verificar_combinacoes(df_ref, max_hoteis, int(0.9*pax_max), df_hoteis, intervalo_hoteis_bairros_iguais, 
                                                             intervalo_hoteis_bairros_diferentes)

                    if lista_combinacao is not None:

                        carro=1

                        roteiro+=1

                        df_ref_2 = df_servicos[mask_servicos & (df_servicos['Est Origem'].isin(lista_combinacao))].reset_index()
                        
                        df_ref_2_group = df_ref_2.groupby('Est Origem').first().sort_values(by='Sequência', ascending=False).reset_index()

                        for index in range(len(df_ref_2_group)):

                            if index==0:

                                df_ref_2_group.at[index, 'Data Horario Apresentacao'] = \
                                    definir_horario_primeiro_hotel(df_ref_2_group, index, intervalo_inicial_orla_maceio, 
                                                                   intervalo_inicial_grande_maceio, intervalo_inicial_maragogi, 
                                                                   intervalo_inicial_santo_antonio, intervalo_inicial_porto)

                            else:

                                intervalo_ref = definir_intervalo_ref(df_ref_2_group, index, intervalo_hoteis_bairros_iguais, 
                                                                      intervalo_hoteis_bairros_diferentes, sequencia_ritz)

                                df_ref_2_group.at[index, 'Data Horario Apresentacao'] = \
                                    df_ref_2_group.at[index-1, 'Data Horario Apresentacao']-intervalo_ref

                        for index, value in df_ref_2_group['Est Origem'].items():

                            df_ref_2.loc[df_ref_2['Est Origem']==value, 'Data Horario Apresentacao'] = \
                                df_ref_2_group.at[index, 'Data Horario Apresentacao']

                        for index, value in df_ref_2['index'].items():

                            df_juncoes_pax_max = pd.concat([df_juncoes_pax_max, df_ref_2.loc[[index]]], ignore_index=True)

                            df_servicos = df_servicos.drop(index=df_ref_2.at[index, 'index'])

                            df_juncoes_pax_max.at[len(df_juncoes_pax_max)-1, 'Roteiro']=roteiro

                            df_juncoes_pax_max.at[len(df_juncoes_pax_max)-1, 'Carros']=carro

                    else:

                        parar_loop=1


            if len(df_hoteis_bus_sem_juncao)>0:

                for index in range(len(df_hoteis_bus_sem_juncao)):

                    voo_ref = df_hoteis_bus_sem_juncao.at[index, 'Voo']

                    if pax_max > 25:

                        mask_servicos = (df_servicos['Bus']=='X') & (df_servicos['Voo']==voo_ref) & \
                            (df_servicos['Modo do Servico']=='REGULAR')
                        
                    else:

                        mask_servicos = (df_servicos['Micro']=='X') & (df_servicos['Voo']==voo_ref) & \
                            (df_servicos['Modo do Servico']=='REGULAR')
                        
                    df_ref = df_servicos[mask_servicos].groupby('Est Origem')\
                                                .agg({'Total ADT | CHD': 'sum', 'Sequência': 'first'})\
                                                    .sort_values(by='Sequência', ascending=False).reset_index()

                    lista_combinacao = verificar_combinacoes(df_ref, max_hoteis, int(0.9*pax_max), df_hoteis, 
                                                             intervalo_hoteis_bairros_iguais, intervalo_hoteis_bairros_diferentes)

                    if lista_combinacao is not None:

                        carro=1

                        roteiro+=1

                        df_ref_2 = df_servicos[mask_servicos & (df_servicos['Est Origem'].isin(lista_combinacao))].reset_index()
                        
                        df_ref_2_group = df_ref_2.groupby('Est Origem').first().sort_values(by='Sequência', ascending=False).reset_index()

                        for index in range(len(df_ref_2_group)):

                            if index==0:

                                df_ref_2_group.at[index, 'Data Horario Apresentacao'] = \
                                    definir_horario_primeiro_hotel(df_ref_2_group, index, intervalo_inicial_orla_maceio, 
                                                                   intervalo_inicial_grande_maceio, intervalo_inicial_maragogi, 
                                                                   intervalo_inicial_santo_antonio, intervalo_inicial_porto)

                            else:

                                intervalo_ref = definir_intervalo_ref(df_ref_2_group, index, intervalo_hoteis_bairros_iguais, 
                                                                      intervalo_hoteis_bairros_diferentes, sequencia_ritz)

                                df_ref_2_group.at[index, 'Data Horario Apresentacao'] = \
                                    df_ref_2_group.at[index-1, 'Data Horario Apresentacao']-intervalo_ref

                        for index, value in df_ref_2_group['Est Origem'].items():

                            df_ref_2.loc[df_ref_2['Est Origem']==value, 'Data Horario Apresentacao'] = \
                                df_ref_2_group.at[index, 'Data Horario Apresentacao']

                        for index, value in df_ref_2['index'].items():

                            df_voos_pax_max = pd.concat([df_voos_pax_max, df_ref_2.loc[[index]]], ignore_index=True)

                            df_servicos = df_servicos.drop(index=df_ref_2.at[index, 'index'])

                            df_voos_pax_max.at[len(df_voos_pax_max)-1, 'Roteiro']=roteiro

                            df_voos_pax_max.at[len(df_voos_pax_max)-1, 'Carros']=carro

                    else:

                        parar_loop=1

            df_servicos = df_servicos.reset_index(drop=True)

            if parar_loop==1:

                break

        else:

            break

    if 'index' in df_juncoes_pax_max.columns.tolist():

        df_juncoes_pax_max = df_juncoes_pax_max.drop(columns=['index'])

    if 'index' in df_voos_pax_max.columns.tolist():

        df_voos_pax_max = df_voos_pax_max.drop(columns=['index'])

    return df_servicos, roteiro, df_juncoes_pax_max, df_voos_pax_max

def roteirizar_privativos(roteiro, df_servicos, index):

    roteiro+=1

    df_servicos.at[index, 'Data Horario Apresentacao'] = \
        definir_horario_primeiro_hotel(df_servicos, index, intervalo_inicial_orla_maceio, intervalo_inicial_grande_maceio, 
                                       intervalo_inicial_maragogi, intervalo_inicial_santo_antonio, intervalo_inicial_porto)
    
    df_servicos.at[index, 'Roteiro'] = roteiro
    
    df_servicos.at[index, 'Carros'] = 1

    return roteiro, df_servicos

def preencher_roteiro_carros(df_servicos, roteiro, carros, value):

    df_servicos.at[value, 'Roteiro'] = roteiro

    df_servicos.at[value, 'Carros'] = carros

    return df_servicos

def abrir_novo_carro(carros, roteiro, df_servicos, value, index, paxs_hotel):

    carros+=1

    df_servicos.at[value, 'Data Horario Apresentacao'] = \
        definir_horario_primeiro_hotel(df_servicos, index, intervalo_inicial_orla_maceio, intervalo_inicial_grande_maceio, 
                                       intervalo_inicial_maragogi, intervalo_inicial_santo_antonio, intervalo_inicial_porto)

    data_horario_primeiro_hotel = df_servicos.at[value, 'Data Horario Apresentacao']

    paxs_total_roteiro = 0

    bairro = ''

    paxs_total_roteiro+=paxs_hotel

    df_servicos.at[value, 'Roteiro'] = roteiro

    df_servicos.at[value, 'Carros'] = carros

    return carros, roteiro, df_servicos, data_horario_primeiro_hotel, bairro, paxs_total_roteiro

def gerar_horarios_apresentacao(df_servicos, roteiro, max_hoteis):

    for index in range(len(df_servicos)):

        # Se o serviço for privativo

        if df_servicos.at[index, 'Modo do Servico']=='PRIVATIVO POR VEICULO' or \
            df_servicos.at[index, 'Modo do Servico']=='PRIVATIVO POR PESSOA' or \
                df_servicos.at[index, 'Modo do Servico']=='EXCLUSIVO':

            roteiro, df_servicos = roteirizar_privativos(roteiro, df_servicos, index)


        # Se o serviço não for privativo

        elif df_servicos.at[index, 'Modo do Servico']=='REGULAR':

            juntar = df_servicos.at[index, 'Junção']

            voo = df_servicos.at[index, 'Voo']

            # Se o voo não estiver em alguma junção

            if pd.isna(juntar):

                df_ref = df_servicos[(df_servicos['Modo do Servico']=='REGULAR') & (df_servicos['Voo']==voo)].reset_index()

                index_inicial = df_ref['index'].min()

                hoteis_mesmo_voo = len(df_ref['Est Origem'].unique().tolist())

                if index==index_inicial:

                    if hoteis_mesmo_voo<=max_hoteis:

                        roteiro+=1

                        carros = 1

                        paxs_total_roteiro = 0

                        bairro = ''

                        # Loop no voo para colocar os horários

                        for index_2, value in df_ref['index'].items():

                            # Se for o primeiro hotel do voo, define o horário inicial, colhe o horário do hotel e inicia somatório de paxs do roteiro

                            if value==index_inicial:

                                df_servicos.at[value, 'Data Horario Apresentacao'] = \
                                    definir_horario_primeiro_hotel(df_servicos, value, intervalo_inicial_orla_maceio, intervalo_inicial_grande_maceio, 
                                   intervalo_inicial_maragogi, intervalo_inicial_santo_antonio, intervalo_inicial_porto)
                                
                                data_horario_primeiro_hotel = df_servicos.at[value, 'Data Horario Apresentacao']
                                
                                paxs_hotel = df_ref[df_ref['Est Origem']==df_servicos.at[value, 'Est Origem']]\
                                    ['Total ADT | CHD'].sum()

                                paxs_total_roteiro+=paxs_hotel

                                df_servicos = preencher_roteiro_carros(df_servicos, roteiro, carros, value)

                            # Se não for a primeira linha do voo, mas o hotel for igual o hotel anterior, só repete o horário de apresentação

                            elif df_servicos.at[value, 'Est Origem']==df_servicos.at[value-1, 'Est Origem']:

                                df_servicos.at[value, 'Data Horario Apresentacao']=\
                                    df_servicos.at[value-1, 'Data Horario Apresentacao']

                                df_servicos = preencher_roteiro_carros(df_servicos, roteiro, carros, value)

                            # Se não for a primeira linha do voo e o hotel não for igual ao anterior

                            else:

                                # Colhe a quantidade de paxs do hotel anterior, o bairro do hotel atual, a quantidade de paxs do hotel atual 
                                # e verifica se estoura a capacidade máxima de um carro

                                paxs_hotel_anterior = paxs_hotel

                                bairro=df_servicos.at[value, 'Região']

                                paxs_hotel = df_ref[df_ref['Est Origem']==df_servicos.at[value, 'Est Origem']]\
                                    ['Total ADT | CHD'].sum()

                                # Se estourar a capacidade do carro, aí trata como se fosse o primeiro hotel e adiciona 1 na variável carros
                                # pra, no final, eu saber quantos carros foram usados nesse roteiro e poder dividir 'igualmente' a quantidade de hoteis

                                if paxs_total_roteiro+paxs_hotel>pax_max:

                                    carros, roteiro, df_servicos, data_horario_primeiro_hotel, bairro, paxs_total_roteiro = \
                                        abrir_novo_carro(carros, roteiro, df_servicos, value, index, paxs_hotel)

                                # Se não estourar a capacidade máxima

                                else:

                                    paxs_total_roteiro+=paxs_hotel

                                    # Sempre que inicia um carro, o bairro fica vazio. Portanto, se não for o primeiro hotel do carro, vai definir a variavel
                                    # intervalo_ref pra o robô saber quantos minutos deve adicionar até o próximo horário de apresentação

                                    if bairro!='':

                                        intervalo_ref = definir_intervalo_ref(df_servicos, value, intervalo_hoteis_bairros_iguais, 
                                                                              intervalo_hoteis_bairros_diferentes, sequencia_ritz)
                                        
                                    if paxs_hotel_anterior>=pax_cinco_min:

                                        intervalo_ref+=intervalo_hoteis_bairros_iguais

                                    data_horario_hotel = df_servicos.at[value-1, 'Data Horario Apresentacao']-\
                                        intervalo_ref

                                    if  data_horario_primeiro_hotel - data_horario_hotel>intervalo_pu_hotel:

                                        carros, roteiro, df_servicos, data_horario_primeiro_hotel, bairro, paxs_total_roteiro = \
                                            abrir_novo_carro(carros, roteiro, df_servicos, value, index, paxs_hotel)

                                    else:

                                        df_servicos.at[value, 'Data Horario Apresentacao']=data_horario_hotel

                                        df_servicos = preencher_roteiro_carros(df_servicos, roteiro, carros, 
                                                                                            value)


                    # Se no voo tiver mais que o número máximo de hoteis permitidos por carro

                    else:

                        roteiro+=1

                        carros = 1

                        paxs_total_roteiro = 0

                        contador_hoteis = 0

                        bairro = ''

                        # Loop no voo para colocar os horários

                        for index_2, value in df_ref['index'].items():

                            # Se for o primeiro hotel do voo, define o horário inicial, colhe o horário do hotel e inicia somatório de paxs do roteiro

                            if value==index_inicial:

                                df_servicos.at[value, 'Data Horario Apresentacao'] = \
                                    definir_horario_primeiro_hotel(df_servicos, value, intervalo_inicial_orla_maceio, intervalo_inicial_grande_maceio, 
                                   intervalo_inicial_maragogi, intervalo_inicial_santo_antonio, intervalo_inicial_porto)
                                
                                data_horario_primeiro_hotel = df_servicos.at[value, 'Data Horario Apresentacao']
                                
                                paxs_hotel = df_ref[df_ref['Est Origem']==df_servicos.at[value, 'Est Origem']]\
                                    ['Total ADT | CHD'].sum()

                                paxs_total_roteiro+=paxs_hotel

                                df_servicos = preencher_roteiro_carros(df_servicos, roteiro, carros, value)

                                contador_hoteis+=1

                            # Se não for a primeira linha do voo, mas o hotel for igual o hotel anterior, só repete o horário de apresentação

                            elif df_servicos.at[value, 'Est Origem']==df_servicos.at[value-1, 'Est Origem']:

                                df_servicos.at[value, 'Data Horario Apresentacao']=\
                                    df_servicos.at[value-1, 'Data Horario Apresentacao']

                                df_servicos = preencher_roteiro_carros(df_servicos, roteiro, carros, value)

                            # Se não for a primeira linha do voo e o hotel não for igual ao anterior

                            else:

                                # Colhe a quantidade de paxs do hotel anterior, o bairro do hotel atual, a quantidade de paxs do hotel atual 
                                # e verifica se estoura a capacidade máxima de um carro

                                contador_hoteis+=1

                                paxs_hotel_anterior = paxs_hotel

                                bairro=df_servicos.at[value, 'Região']

                                paxs_hotel = df_ref[df_ref['Est Origem']==df_servicos.at[value, 'Est Origem']]\
                                    ['Total ADT | CHD'].sum()

                                if contador_hoteis>max_hoteis:

                                    carros, roteiro, df_servicos, data_horario_primeiro_hotel, bairro, paxs_total_roteiro = \
                                        abrir_novo_carro(carros, roteiro, df_servicos, value, index, paxs_hotel)
                                    
                                    contador_hoteis = 1
                                    
                                else:

                                    # Se estourar a capacidade do carro, aí trata como se fosse o primeiro hotel e adiciona 1 na variável carros
                                    # pra, no final, eu saber quantos carros foram usados nesse roteiro e poder dividir 'igualmente' a quantidade de hoteis

                                    if paxs_total_roteiro+paxs_hotel>pax_max:

                                        carros, roteiro, df_servicos, data_horario_primeiro_hotel, bairro, paxs_total_roteiro = \
                                            abrir_novo_carro(carros, roteiro, df_servicos, value, index, paxs_hotel)
                                        
                                        contador_hoteis = 1

                                    # Se não estourar a capacidade máxima

                                    else:

                                        paxs_total_roteiro+=paxs_hotel

                                        # Sempre que inicia um carro, o bairro fica vazio. Portanto, se não for o primeiro hotel do carro, vai definir a variavel
                                        # intervalo_ref pra o robô saber quantos minutos deve adicionar até o próximo horário de apresentação

                                        if bairro!='':

                                            intervalo_ref = definir_intervalo_ref(df_servicos, value, intervalo_hoteis_bairros_iguais, 
                                                                                  intervalo_hoteis_bairros_diferentes, sequencia_ritz)
                                            
                                        if paxs_hotel_anterior>=pax_cinco_min:

                                            intervalo_ref+=intervalo_hoteis_bairros_iguais

                                        data_horario_hotel = df_servicos.at[value-1, 'Data Horario Apresentacao']-\
                                            intervalo_ref

                                        if  data_horario_primeiro_hotel - data_horario_hotel>intervalo_pu_hotel:

                                            carros, roteiro, df_servicos, data_horario_primeiro_hotel, bairro, paxs_total_roteiro = \
                                            abrir_novo_carro(carros, roteiro, df_servicos, value, index, paxs_hotel)
                                            
                                            contador_hoteis = 1

                                        else:

                                            df_servicos.at[value, 'Data Horario Apresentacao']=data_horario_hotel

                                            df_servicos = preencher_roteiro_carros(df_servicos, roteiro, 
                                                                                                carros, value)
    
            # Se o voo estiver em alguma junção

            else:

                df_ref = df_servicos[(df_servicos['Modo do Servico']=='REGULAR') & (df_servicos['Junção']==juntar)].reset_index()

                index_inicial = df_ref['index'].min()

                hoteis_mesma_juncao = len(df_ref['Est Origem'].unique().tolist())

                if index==index_inicial:

                    if hoteis_mesma_juncao<=max_hoteis:

                        roteiro+=1

                        carros = 1

                        paxs_total_roteiro = 0

                        bairro = ''

                        # Loop no voo para colocar os horários

                        for index_2, value in df_ref['index'].items():

                            # Se for o primeiro hotel do voo, define o horário inicial, colhe o horário do hotel e inicia somatório de paxs do roteiro

                            if value==index_inicial:

                                df_servicos.at[value, 'Data Horario Apresentacao']=\
                                    definir_horario_primeiro_hotel(df_servicos, value, intervalo_inicial_orla_maceio, intervalo_inicial_grande_maceio, 
                                   intervalo_inicial_maragogi, intervalo_inicial_santo_antonio, intervalo_inicial_porto)
                                
                                data_horario_primeiro_hotel = df_servicos.at[value, 'Data Horario Apresentacao']
                                
                                paxs_hotel = df_ref[df_ref['Est Origem']==df_servicos.at[value, 'Est Origem']]\
                                    ['Total ADT | CHD'].sum()

                                paxs_total_roteiro+=paxs_hotel

                                df_servicos = preencher_roteiro_carros(df_servicos, roteiro, carros, value)

                            # Se não for a primeira linha do voo, mas o hotel for igual o hotel anterior, só repete o horário de apresentação

                            elif df_servicos.at[value, 'Est Origem']==df_servicos.at[value-1, 'Est Origem']:

                                df_servicos.at[value, 'Data Horario Apresentacao']=\
                                    df_servicos.at[value-1, 'Data Horario Apresentacao']

                                df_servicos = preencher_roteiro_carros(df_servicos, roteiro, carros, value)

                            # Se não for a primeira linha do voo e o hotel não for igual ao anterior

                            else:

                                # Colhe a quantidade de paxs do hotel anterior, o bairro do hotel atual, a quantidade de paxs do hotel atual 
                                # e verifica se estoura a capacidade máxima de um carro

                                paxs_hotel_anterior = paxs_hotel

                                bairro=df_servicos.at[value, 'Região']

                                paxs_hotel = df_ref[df_ref['Est Origem']==df_servicos.at[value, 'Est Origem']]\
                                    ['Total ADT | CHD'].sum()

                                # Se estourar a capacidade do carro, aí trata como se fosse o primeiro hotel e adiciona 1 na variável carros
                                # pra, no final, eu saber quantos carros foram usados nesse roteiro e poder dividir 'igualmente' a quantidade de hoteis

                                if paxs_total_roteiro+paxs_hotel>pax_max:

                                    carros, roteiro, df_servicos, data_horario_primeiro_hotel, bairro, paxs_total_roteiro = \
                                        abrir_novo_carro(carros, roteiro, df_servicos, value, index, paxs_hotel)

                                # Se não estourar a capacidade máxima

                                else:

                                    paxs_total_roteiro+=paxs_hotel

                                    # Sempre que inicia um carro, o bairro fica vazio. Portanto, se não for o primeiro hotel do carro, vai definir a variavel
                                    # intervalo_ref pra o robô saber quantos minutos deve adicionar até o próximo horário de apresentação

                                    if bairro!='':

                                        intervalo_ref = definir_intervalo_ref(df_servicos, value, intervalo_hoteis_bairros_iguais, 
                                                                              intervalo_hoteis_bairros_diferentes, sequencia_ritz)
                                        
                                    if paxs_hotel_anterior>=pax_cinco_min:

                                        intervalo_ref+=intervalo_hoteis_bairros_iguais

                                    data_horario_hotel = df_servicos.at[value-1, 'Data Horario Apresentacao']-\
                                        intervalo_ref

                                    if  data_horario_primeiro_hotel - data_horario_hotel>intervalo_pu_hotel:

                                        carros, roteiro, df_servicos, data_horario_primeiro_hotel, bairro, paxs_total_roteiro = \
                                            abrir_novo_carro(carros, roteiro, df_servicos, value, index, paxs_hotel)

                                    else:

                                        df_servicos.at[value, 'Data Horario Apresentacao']=data_horario_hotel

                                        df_servicos = preencher_roteiro_carros(df_servicos, roteiro, carros, value)

                    else:

                        roteiro+=1

                        carros = 1

                        paxs_total_roteiro = 0

                        contador_hoteis = 0

                        bairro = ''

                        # Loop no voo para colocar os horários

                        for index_2, value in df_ref['index'].items():

                            # Se for o primeiro hotel do voo, define o horário inicial, colhe o horário do hotel e inicia somatório de paxs do roteiro

                            if value==index_inicial:

                                df_servicos.at[value, 'Data Horario Apresentacao']=\
                                    definir_horario_primeiro_hotel(df_servicos, value, intervalo_inicial_orla_maceio, intervalo_inicial_grande_maceio, 
                                   intervalo_inicial_maragogi, intervalo_inicial_santo_antonio, intervalo_inicial_porto)
                                
                                data_horario_primeiro_hotel = df_servicos.at[value, 'Data Horario Apresentacao']
                                
                                paxs_hotel = df_ref[df_ref['Est Origem']==df_servicos.at[value, 'Est Origem']]\
                                    ['Total ADT | CHD'].sum()

                                paxs_total_roteiro+=paxs_hotel

                                df_servicos = preencher_roteiro_carros(df_servicos, roteiro, carros, value)

                                contador_hoteis+=1

                            # Se não for a primeira linha do voo, mas o hotel for igual o hotel anterior, só repete o horário de apresentação

                            elif df_servicos.at[value, 'Est Origem']==df_servicos.at[value-1, 'Est Origem']:

                                df_servicos.at[value, 'Data Horario Apresentacao']=\
                                    df_servicos.at[value-1, 'Data Horario Apresentacao']

                                df_servicos = preencher_roteiro_carros(df_servicos, roteiro, carros, value)

                            # Se não for a primeira linha do voo e o hotel não for igual ao anterior

                            else:

                                # Colhe a quantidade de paxs do hotel anterior, o bairro do hotel atual, a quantidade de paxs do hotel atual 
                                # e verifica se estoura a capacidade máxima de um carro

                                contador_hoteis+=1

                                paxs_hotel_anterior = paxs_hotel

                                bairro=df_servicos.at[value, 'Região']

                                paxs_hotel = df_ref[df_ref['Est Origem']==df_servicos.at[value, 'Est Origem']]\
                                    ['Total ADT | CHD'].sum()

                                if contador_hoteis>max_hoteis:

                                    carros, roteiro, df_servicos, data_horario_primeiro_hotel, bairro, paxs_total_roteiro = \
                                        abrir_novo_carro(carros, roteiro, df_servicos, value, index, paxs_hotel)
                                    
                                    contador_hoteis = 1
                                    
                                else:

                                    # Se estourar a capacidade do carro, aí trata como se fosse o primeiro hotel e adiciona 1 na variável carros
                                    # pra, no final, eu saber quantos carros foram usados nesse roteiro e poder dividir 'igualmente' a quantidade de hoteis

                                    if paxs_total_roteiro+paxs_hotel>pax_max:

                                        carros, roteiro, df_servicos, data_horario_primeiro_hotel, bairro, paxs_total_roteiro = \
                                            abrir_novo_carro(carros, roteiro, df_servicos, value, index, paxs_hotel)
                                        
                                        contador_hoteis = 1

                                    # Se não estourar a capacidade máxima

                                    else:

                                        paxs_total_roteiro+=paxs_hotel

                                        # Sempre que inicia um carro, o bairro fica vazio. Portanto, se não for o primeiro hotel do carro, vai definir a variavel
                                        # intervalo_ref pra o robô saber quantos minutos deve adicionar até o próximo horário de apresentação

                                        if bairro!='':

                                            intervalo_ref = definir_intervalo_ref(df_servicos, value, intervalo_hoteis_bairros_iguais, 
                                                                                  intervalo_hoteis_bairros_diferentes, sequencia_ritz)
                                            
                                        if paxs_hotel_anterior>=pax_cinco_min:

                                            intervalo_ref+=intervalo_hoteis_bairros_iguais

                                        data_horario_hotel = df_servicos.at[value-1, 'Data Horario Apresentacao']-\
                                            intervalo_ref

                                        if  data_horario_primeiro_hotel - data_horario_hotel>intervalo_pu_hotel:

                                            carros, roteiro, df_servicos, data_horario_primeiro_hotel, bairro, paxs_total_roteiro = \
                                            abrir_novo_carro(carros, roteiro, df_servicos, value, index, paxs_hotel)
                                            
                                            contador_hoteis = 1

                                        else:

                                            df_servicos.at[value, 'Data Horario Apresentacao']=data_horario_hotel

                                            df_servicos = preencher_roteiro_carros(df_servicos, roteiro, carros, value)

    return df_servicos, roteiro

def gerar_roteiros_alternativos(df_servicos, max_hoteis_ref):

    df_roteiros_alternativos = pd.DataFrame(columns=df_servicos.columns.tolist())

    lista_roteiros_alternativos = df_servicos[df_servicos['Carros']==2]['Roteiro'].unique().tolist()

    # Gerando roteiros alternativos

    for item in lista_roteiros_alternativos:

        df_ref = df_servicos[df_servicos['Roteiro']==item].reset_index(drop=True)

        divisao_inteira = len(df_ref['Est Origem'].unique().tolist()) // df_ref['Carros'].max()

        if len(df_ref['Est Origem'].unique().tolist()) % df_ref['Carros'].max() == 0:

            max_hoteis = divisao_inteira

        else:

            max_hoteis = divisao_inteira + 1

        if max_hoteis!=max_hoteis_ref:

            carros = 1
    
            paxs_total_roteiro = 0
    
            contador_hoteis = 0
    
            bairro = ''
    
            for index in range(len(df_ref)):
    
                # Se for o primeiro hotel do voo, define o horário inicial, colhe o horário do hotel e inicia somatório de paxs do roteiro
    
                if index==0:
    
                    df_ref.at[index, 'Data Horario Apresentacao']=definir_horario_primeiro_hotel(df_ref, index, intervalo_inicial_orla_maceio, intervalo_inicial_grande_maceio, 
                                   intervalo_inicial_maragogi, intervalo_inicial_santo_antonio, intervalo_inicial_porto)
                    
                    data_horario_primeiro_hotel = df_ref.at[index, 'Data Horario Apresentacao']
                    
                    paxs_hotel = df_ref[df_ref['Est Origem']==df_ref.at[index, 'Est Origem']]['Total ADT | CHD'].sum()
    
                    paxs_total_roteiro+=paxs_hotel
    
                    df_ref = preencher_roteiro_carros(df_ref, item, carros, index)
    
                    contador_hoteis+=1
    
                # Se não for a primeira linha do voo, mas o hotel for igual o hotel anterior, só repete o horário de apresentação
    
                elif df_ref.at[index, 'Est Origem']==df_ref.at[index-1, 'Est Origem']:
    
                    df_ref.at[index, 'Data Horario Apresentacao']=df_ref.at[index-1, 'Data Horario Apresentacao']
    
                    df_ref = preencher_roteiro_carros(df_ref, item, carros, index)
    
                # Se não for a primeira linha do voo e o hotel não for igual ao anterior
    
                else:
    
                    # Colhe a quantidade de paxs do hotel anterior, o bairro do hotel atual, a quantidade de paxs do hotel atual 
                    # e verifica se estoura a capacidade máxima de um carro
    
                    contador_hoteis+=1
    
                    if contador_hoteis>max_hoteis:
    
                        carros+=1
    
                        df_ref.at[index, 'Data Horario Apresentacao']=definir_horario_primeiro_hotel(df_ref, index, intervalo_inicial_orla_maceio, intervalo_inicial_grande_maceio, 
                                   intervalo_inicial_maragogi, intervalo_inicial_santo_antonio, intervalo_inicial_porto)
                        
                        paxs_hotel = df_ref[df_ref['Est Origem']==df_ref.at[index, 'Est Origem']]['Total ADT | CHD'].sum()
    
                        data_horario_primeiro_hotel = df_ref.at[index, 'Data Horario Apresentacao']
    
                        paxs_total_roteiro = 0
    
                        bairro = ''
    
                        paxs_total_roteiro+=paxs_hotel
    
                        df_ref.at[index, 'Roteiro'] = item
    
                        df_ref.at[index, 'Carros'] = carros
                        
                        contador_hoteis = 1
                        
                    else:

                        paxs_hotel_anterior = paxs_hotel
    
                        bairro=df_ref.at[index, 'Região']
    
                        paxs_hotel = df_ref[df_ref['Est Origem']==df_ref.at[index, 'Est Origem']]['Total ADT | CHD'].sum()
    
                        # Se estourar a capacidade do carro, aí trata como se fosse o primeiro hotel e adiciona 1 na variável carros
                        # pra, no final, eu saber quantos carros foram usados nesse roteiro e poder dividir 'igualmente' a quantidade de hoteis
    
                        if paxs_total_roteiro+paxs_hotel>pax_max:
    
                            carros+=1
    
                            df_ref.at[index, 'Data Horario Apresentacao']=definir_horario_primeiro_hotel(df_ref, index, intervalo_inicial_orla_maceio, intervalo_inicial_grande_maceio, 
                                   intervalo_inicial_maragogi, intervalo_inicial_santo_antonio, intervalo_inicial_porto)
    
                            data_horario_primeiro_hotel = df_ref.at[index, 'Data Horario Apresentacao']
    
                            paxs_total_roteiro = 0
    
                            bairro = ''
    
                            paxs_total_roteiro+=paxs_hotel
    
                            df_ref.at[index, 'Roteiro'] = item
    
                            df_ref.at[index, 'Carros'] = carros
                            
                            contador_hoteis = 1
    
                        # Se não estourar a capacidade máxima
    
                        else:
    
                            paxs_total_roteiro+=paxs_hotel
    
                            # Sempre que inicia um carro, o bairro fica vazio. Portanto, se não for o primeiro hotel do carro, vai definir a variavel
                            # intervalo_ref pra o robô saber quantos minutos deve adicionar até o próximo horário de apresentação
    
                            if bairro!='':
    
                                intervalo_ref = definir_intervalo_ref(df_ref, index, intervalo_hoteis_bairros_iguais, 
                                                                      intervalo_hoteis_bairros_diferentes, sequencia_ritz)
                                
                            if paxs_hotel_anterior>=pax_cinco_min:

                                intervalo_ref+=intervalo_hoteis_bairros_iguais
    
                            data_horario_hotel = df_ref.at[index-1, 'Data Horario Apresentacao']-intervalo_ref
    
                            if data_horario_primeiro_hotel - data_horario_hotel>intervalo_pu_hotel:
    
                                carros+=1
    
                                df_ref.at[index, 'Data Horario Apresentacao']=definir_horario_primeiro_hotel(df_ref, index, intervalo_inicial_orla_maceio, intervalo_inicial_grande_maceio, 
                                   intervalo_inicial_maragogi, intervalo_inicial_santo_antonio, intervalo_inicial_porto)
    
                                data_horario_primeiro_hotel = df_ref.at[index, 'Data Horario Apresentacao']
    
                                paxs_total_roteiro = 0
    
                                bairro = ''
    
                                paxs_total_roteiro+=paxs_hotel
    
                                df_ref.at[index, 'Roteiro'] = item
    
                                df_ref.at[index, 'Carros'] = carros
                                
                                contador_hoteis = 1
    
                            else:
    
                                df_ref.at[index, 'Data Horario Apresentacao']=data_horario_hotel
    
                                df_ref = preencher_roteiro_carros(df_ref, item, carros, index)
    
            df_roteiros_alternativos = pd.concat([df_roteiros_alternativos, df_ref], ignore_index=True)

    return df_roteiros_alternativos

def gerar_roteiros_alternativos_2(df_servicos, max_hoteis_ref, intervalo_pu_hotel):

    df_roteiros_alternativos = pd.DataFrame(columns=df_servicos.columns.tolist())
    
    lista_roteiros_alternativos = df_servicos[df_servicos['Carros']==2]['Roteiro'].unique().tolist()

    for item in lista_roteiros_alternativos:

        df_ref = df_servicos[df_servicos['Roteiro']==item].reset_index(drop=True)

        n_hoteis = len(df_ref['Est Origem'].unique().tolist())

        if n_hoteis<=max_hoteis_ref:

            carros = 1
    
            paxs_total_roteiro = 0
    
            contador_hoteis = 0
    
            bairro = ''
    
            for index in range(len(df_ref)):
    
                # Se for o primeiro hotel do voo, define o horário inicial, colhe o horário do hotel e inicia somatório de paxs do roteiro
    
                if index==0:
    
                    df_ref.at[index, 'Data Horario Apresentacao']=definir_horario_primeiro_hotel(df_ref, index, intervalo_inicial_orla_maceio, intervalo_inicial_grande_maceio, 
                                   intervalo_inicial_maragogi, intervalo_inicial_santo_antonio, intervalo_inicial_porto)
                    
                    data_horario_primeiro_hotel = df_ref.at[index, 'Data Horario Apresentacao']
                    
                    paxs_hotel = df_ref[df_ref['Est Origem']==df_ref.at[index, 'Est Origem']]['Total ADT | CHD'].sum()
    
                    paxs_total_roteiro+=paxs_hotel
    
                    df_ref = preencher_roteiro_carros(df_ref, item, carros, index)
    
                    contador_hoteis+=1
    
                # Se não for a primeira linha do voo, mas o hotel for igual o hotel anterior, só repete o horário de apresentação
    
                elif df_ref.at[index, 'Est Origem']==df_ref.at[index-1, 'Est Origem']:
    
                    df_ref.at[index, 'Data Horario Apresentacao']=df_ref.at[index-1, 'Data Horario Apresentacao']
    
                    df_ref = preencher_roteiro_carros(df_ref, item, carros, index)
    
                # Se não for a primeira linha do voo e o hotel não for igual ao anterior
    
                else:
    
                    # Colhe a quantidade de paxs do hotel anterior, o bairro do hotel atual, a quantidade de paxs do hotel atual 
                    # e verifica se estoura a capacidade máxima de um carro
    
                    contador_hoteis+=1
    
                    if contador_hoteis>max_hoteis:
    
                        carros+=1
    
                        df_ref.at[index, 'Data Horario Apresentacao']=definir_horario_primeiro_hotel(df_ref, index, intervalo_inicial_orla_maceio, intervalo_inicial_grande_maceio, 
                                   intervalo_inicial_maragogi, intervalo_inicial_santo_antonio, intervalo_inicial_porto)
                        
                        paxs_hotel = df_ref[df_ref['Est Origem']==df_ref.at[index, 'Est Origem']]['Total ADT | CHD'].sum()
    
                        data_horario_primeiro_hotel = df_ref.at[index, 'Data Horario Apresentacao']
    
                        paxs_total_roteiro = 0
    
                        bairro = ''
    
                        paxs_total_roteiro+=paxs_hotel
    
                        df_ref.at[index, 'Roteiro'] = item
    
                        df_ref.at[index, 'Carros'] = carros
                        
                        contador_hoteis = 1
                        
                    else:

                        paxs_hotel_anterior = paxs_hotel
    
                        bairro=df_ref.at[index, 'Região']
    
                        paxs_hotel = df_ref[df_ref['Est Origem']==df_ref.at[index, 'Est Origem']]['Total ADT | CHD'].sum()
    
                        # Se estourar a capacidade do carro, aí trata como se fosse o primeiro hotel e adiciona 1 na variável carros
                        # pra, no final, eu saber quantos carros foram usados nesse roteiro e poder dividir 'igualmente' a quantidade de hoteis
    
                        if paxs_total_roteiro+paxs_hotel>pax_max:
    
                            carros+=1
    
                            df_ref.at[index, 'Data Horario Apresentacao']=definir_horario_primeiro_hotel(df_ref, index, intervalo_inicial_orla_maceio, intervalo_inicial_grande_maceio, 
                                   intervalo_inicial_maragogi, intervalo_inicial_santo_antonio, intervalo_inicial_porto)
    
                            data_horario_primeiro_hotel = df_ref.at[index, 'Data Horario Apresentacao']
    
                            paxs_total_roteiro = 0
    
                            bairro = ''
    
                            paxs_total_roteiro+=paxs_hotel
    
                            df_ref.at[index, 'Roteiro'] = item
    
                            df_ref.at[index, 'Carros'] = carros
                            
                            contador_hoteis = 1
    
                        # Se não estourar a capacidade máxima
    
                        else:
    
                            paxs_total_roteiro+=paxs_hotel
    
                            # Sempre que inicia um carro, o bairro fica vazio. Portanto, se não for o primeiro hotel do carro, vai definir a variavel
                            # intervalo_ref pra o robô saber quantos minutos deve adicionar até o próximo horário de apresentação
    
                            if bairro!='':
    
                                intervalo_ref = definir_intervalo_ref(df_ref, index, intervalo_hoteis_bairros_iguais, 
                                                                      intervalo_hoteis_bairros_diferentes, sequencia_ritz)
                                
                            if paxs_hotel_anterior>=pax_cinco_min:

                                intervalo_ref+=intervalo_hoteis_bairros_iguais
    
                            data_horario_hotel = df_ref.at[index-1, 'Data Horario Apresentacao']-intervalo_ref
    
                            if data_horario_primeiro_hotel - data_horario_hotel>intervalo_pu_hotel:
    
                                carros+=1
    
                                df_ref.at[index, 'Data Horario Apresentacao']=definir_horario_primeiro_hotel(df_ref, index, intervalo_inicial_orla_maceio, intervalo_inicial_grande_maceio, 
                                   intervalo_inicial_maragogi, intervalo_inicial_santo_antonio, intervalo_inicial_porto)
    
                                data_horario_primeiro_hotel = df_ref.at[index, 'Data Horario Apresentacao']
    
                                paxs_total_roteiro = 0
    
                                bairro = ''
    
                                paxs_total_roteiro+=paxs_hotel
    
                                df_ref.at[index, 'Roteiro'] = item
    
                                df_ref.at[index, 'Carros'] = carros
                                
                                contador_hoteis = 1
    
                            else:
    
                                df_ref.at[index, 'Data Horario Apresentacao']=data_horario_hotel
    
                                df_ref = preencher_roteiro_carros(df_ref, item, carros, index)

            if df_ref['Carros'].max()==1:
    
                df_roteiros_alternativos = pd.concat([df_roteiros_alternativos, df_ref], ignore_index=True)

    return df_roteiros_alternativos

def identificar_apoios_em_df(df_servicos):

    df_servicos['Apoios'] = ''

    for n_roteiro in df_servicos['Roteiro'].unique().tolist():

        df_ref = df_servicos[df_servicos['Roteiro']==n_roteiro].reset_index()

        for veiculo in df_ref['Carros'].unique().tolist():

            df_ref_2 = df_ref[df_ref['Carros']==veiculo].reset_index(drop=True)

            pax_carro = df_ref[df_ref['Carros']==veiculo]['Total ADT | CHD'].sum()

            limitacao_micro = df_ref_2['Micro'].isnull().any()

            limitacao_bus = df_ref_2['Bus'].isnull().any()

            if pax_carro>12 and pax_carro<=25 and limitacao_micro:

                df_ref_3 = df_ref_2[pd.isna(df_ref_2['Micro'])].reset_index(drop=True)

                for index in df_ref_3['index'].tolist():

                    df_servicos.at[index, 'Apoios']='X'

            elif pax_carro>25 and limitacao_bus:

                df_ref_3 = df_ref_2[pd.isna(df_ref_2['Bus'])].reset_index(drop=True)

                for index in df_ref_3['index'].tolist():

                    df_servicos.at[index, 'Apoios']='X'

    return df_servicos

def gerar_roteiros_apoio(df_servicos):

    df_roteiros_apoios = df_servicos[df_servicos['Apoios']=='X'].reset_index()

    df_roteiros_apoios['Carros Apoios']=''

    df_roteiros_carros = df_roteiros_apoios[['Roteiro', 'Carros']].drop_duplicates()

    for index, value in df_roteiros_carros['Roteiro'].items():

        veiculo = df_roteiros_carros.at[index, 'Carros']

        df_ref = df_servicos[(df_servicos['Roteiro']==value) & 
                                        (df_servicos['Carros']==veiculo)].reset_index()

        df_ref_apoios = df_ref[df_ref['Apoios']=='X'].reset_index(drop=True)

        carros = 1

        paxs_total_roteiro = 0

        contador_hoteis = 0

        bairro = ''

        for index in range(len(df_ref_apoios)):

            # Se for o primeiro hotel do voo, define o horário inicial, colhe o horário do hotel e inicia somatório de paxs do roteiro

            if index==0:

                df_ref_apoios.at[index, 'Data Horario Apresentacao']=definir_horario_primeiro_hotel(df_ref_apoios, index, intervalo_inicial_orla_maceio, intervalo_inicial_grande_maceio, 
                                   intervalo_inicial_maragogi, intervalo_inicial_santo_antonio, intervalo_inicial_porto)

                df_ref_apoios.at[index, 'Data Horario Apresentacao']-=intervalo_hoteis_bairros_iguais
                
                paxs_hotel = df_ref_apoios[df_ref_apoios['Est Origem']==df_ref_apoios.at[index, 'Est Origem']]['Total ADT | CHD'].sum()

                paxs_total_roteiro+=paxs_hotel

                df_ref_apoios = preencher_roteiro_carros(df_ref_apoios, value, carros, index)

                contador_hoteis+=1

            # Se não for a primeira linha do voo, mas o hotel for igual o hotel anterior, só repete o horário de apresentação

            elif df_ref_apoios.at[index, 'Est Origem']==df_ref_apoios.at[index-1, 'Est Origem']:

                df_ref_apoios.at[index, 'Data Horario Apresentacao']=df_ref_apoios.at[index-1, 'Data Horario Apresentacao']

                df_ref_apoios = preencher_roteiro_carros(df_ref_apoios, value, carros, index)

            # Se não for a primeira linha do voo e o hotel não for igual ao anterior

            else:

                paxs_hotel_anterior = paxs_hotel

                bairro=df_ref_apoios.at[index, 'Região']

                paxs_hotel = df_ref_apoios[df_ref_apoios['Est Origem']==df_ref_apoios.at[index, 'Est Origem']]['Total ADT | CHD'].sum()

                # Se estourar a capacidade do carro, aí trata como se fosse o primeiro hotel e adiciona 1 na variável carros
                # pra, no final, eu saber quantos carros foram usados nesse roteiro e poder dividir 'igualmente' a quantidade de hoteis

                if paxs_total_roteiro+paxs_hotel>12:

                    carros+=1

                    df_ref_apoios.at[index, 'Data Horario Apresentacao']=definir_horario_primeiro_hotel(df_ref_apoios, index, intervalo_inicial_orla_maceio, intervalo_inicial_grande_maceio, 
                                   intervalo_inicial_maragogi, intervalo_inicial_santo_antonio, intervalo_inicial_porto)

                    paxs_total_roteiro = 0

                    bairro = ''

                    paxs_total_roteiro+=paxs_hotel

                    df_ref_apoios.at[index, 'Roteiro'] = value

                    df_ref_apoios.at[index, 'Carros'] = carros

                # Se não estourar a capacidade máxima

                else:

                    paxs_total_roteiro+=paxs_hotel

                    # Sempre que inicia um carro, o bairro fica vazio. Portanto, se não for o primeiro hotel do carro, vai definir a variavel
                    # intervalo_ref pra o robô saber quantos minutos deve adicionar até o próximo horário de apresentação

                    if bairro!='':

                        intervalo_ref = definir_intervalo_ref(df_ref_apoios, index, intervalo_hoteis_bairros_iguais, 
                                                              intervalo_hoteis_bairros_diferentes, sequencia_ritz)
                        
                    if paxs_hotel_anterior>=pax_cinco_min:

                        intervalo_ref+=intervalo_hoteis_bairros_iguais

                    data_horario_hotel = df_ref_apoios.at[index-1, 'Data Horario Apresentacao']-intervalo_ref

                    df_ref_apoios.at[index, 'Data Horario Apresentacao']=data_horario_hotel

                    df_ref_apoios = preencher_roteiro_carros(df_ref_apoios, value, carros, index)


        for index, value in df_ref_apoios['index'].items():

            df_roteiros_apoios.loc[df_roteiros_apoios['index']==value, 'Data Horario Apresentacao']=\
                df_ref_apoios.at[index, 'Data Horario Apresentacao']

            df_roteiros_apoios.loc[df_roteiros_apoios['index']==value, 'Carros Apoios']=df_ref_apoios.at[index, 'Carros']

            df_servicos.at[value, 'Data Horario Apresentacao']=df_ref_apoios.at[index, 'Data Horario Apresentacao']

    if 'index' in df_roteiros_apoios.columns.tolist():

        df_roteiros_apoios = df_roteiros_apoios.drop(columns=['index'])

    return df_servicos, df_roteiros_apoios

def plotar_roteiros_simples(df_servicos, row3, coluna):

    for item in df_servicos['Roteiro'].unique().tolist():

        df_ref_1 = df_servicos[df_servicos['Roteiro']==item].reset_index(drop=True)

        horario_inicial_voo = df_ref_1['Horario Voo'].min()

        horario_final_voo = df_ref_1['Horario Voo'].max()

        if horario_inicial_voo == horario_final_voo:

            titulo_voos = f'{horario_inicial_voo}'

        else:

            titulo_voos = f'{horario_inicial_voo} às {horario_final_voo}'

        lista_nome_voos = df_ref_1['Voo'].unique().tolist()

        voos_unidos = ' + '.join(lista_nome_voos)

        for carro in df_ref_1['Carros'].unique().tolist():

            df_ref_2 = df_ref_1[df_ref_1['Carros']==carro].reset_index(drop=True)

            modo = df_ref_2.at[0, 'Modo do Servico']

            paxs_total = int(df_ref_2['Total ADT | CHD'].sum())

            if modo=='REGULAR':
    
                titulo_roteiro = f'Roteiro {item}'

                titulo_carro = f'Veículo {carro}'

                titulo_modo_voo_pax = f'*{modo.title()} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'

            else:

                reserva = df_ref_2.at[0, 'Reserva']

                titulo_roteiro = f'Roteiro {item}'

                titulo_carro = f'Veículo {carro}'

                titulo_modo_voo_pax = f'*{modo.title()} | {reserva} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'

            df_ref_3 = df_ref_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first'})\
                .sort_values(by='Data Horario Apresentacao').reset_index()
        
            with row3[coluna]:

                container = st.container(border=True, height=500)

                container.header(titulo_roteiro)

                container.subheader(titulo_carro)

                container.markdown(titulo_modo_voo_pax)

                container.dataframe(df_ref_3[['Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)

                if coluna==2:

                    coluna=0

                else:

                    coluna+=1

    return coluna

def plotar_roteiros_gerais(df_servicos, df_apoios, df_alternativos, df_apoios_alternativos, coluna, row3):

    for item in df_servicos['Roteiro'].unique().tolist():

        if not item in df_alternativos['Roteiro'].unique().tolist():

            df_ref_1 = df_servicos[df_servicos['Roteiro']==item].reset_index(drop=True)
    
            horario_inicial_voo = df_ref_1['Horario Voo'].min()
    
            horario_final_voo = df_ref_1['Horario Voo'].max()
    
            if horario_inicial_voo == horario_final_voo:
    
                titulo_voos = f'{horario_inicial_voo}'
    
            else:
    
                titulo_voos = f'{horario_inicial_voo} às {horario_final_voo}'

            lista_nome_voos = df_ref_1['Voo'].unique().tolist()

            voos_unidos = ' + '.join(lista_nome_voos)
    
            for carro in df_ref_1['Carros'].unique().tolist():
    
                df_ref_2 = df_ref_1[df_ref_1['Carros']==carro].reset_index(drop=True)
    
                modo = df_ref_2.at[0, 'Modo do Servico']
    
                paxs_total = int(df_ref_2['Total ADT | CHD'].sum())
    
                if modo=='REGULAR':
    
                    titulo_roteiro = f'Roteiro {item}'
    
                    titulo_carro = f'Veículo {carro}'
    
                    titulo_modo_voo_pax = f'*{modo.title()} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'
    
                else:
    
                    reserva = df_ref_2.at[0, 'Reserva']
    
                    titulo_roteiro = f'Roteiro {item}'
    
                    titulo_carro = f'Veículo {carro}'
    
                    titulo_modo_voo_pax = f'*{modo.title()} | {reserva} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'
    
                lista_apoios = df_ref_2['Apoios'].unique().tolist()
    
                if 'X' in lista_apoios:
    
                    df_ref_3 = df_ref_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first', 'Apoios': 'first'})\
                        .sort_values(by='Data Horario Apresentacao').reset_index()
                else:
    
                    df_ref_3 = df_ref_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first'})\
                        .sort_values(by='Data Horario Apresentacao').reset_index()
            
                with row3[coluna]:
    
                    container = st.container(border=True, height=500)
    
                    container.header(titulo_roteiro)
    
                    container.subheader(titulo_carro)
    
                    container.markdown(titulo_modo_voo_pax)
    
                    if 'X' in lista_apoios:
    
                        container.dataframe(df_ref_3[['Apoios', 'Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)
    
                    else:
    
                        container.dataframe(df_ref_3[['Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)
    
                    if coluna==2:
    
                        coluna=0
    
                    else:
    
                        coluna+=1
    
                df_ref_apoio = df_apoios[(df_apoios['Roteiro']==item) & (df_apoios['Carros']==carro)].reset_index(drop=True)
    
                if len(df_ref_apoio)>0:
    
                    for carro_2 in df_ref_apoio['Carros Apoios'].unique().tolist():
    
                        df_ref_apoio_2 = df_ref_apoio[df_ref_apoio['Carros Apoios']==carro_2].reset_index(drop=True)
    
                        paxs_total = int(df_ref_apoio_2['Total ADT | CHD'].sum())
    
                        titulo_roteiro = f'Apoio | Roteiro {item}'
    
                        titulo_carro_principal = f'Veículo Principal {carro}'
    
                        titulo_carro = f'Veículo Apoio {carro_2}'
    
                        titulo_modo_voo_pax = f'*{modo.title()} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'
    
                        df_ref_apoio_3 = df_ref_apoio_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first'})\
                            .sort_values(by='Data Horario Apresentacao').reset_index()
                        
                        with row3[coluna]:
    
                            container = st.container(border=True, height=500)
    
                            container.header(titulo_roteiro)
    
                            container.subheader(titulo_carro_principal)
    
                            container.subheader(titulo_carro)
    
                            container.markdown(titulo_modo_voo_pax)
    
                            container.dataframe(df_ref_apoio_3[['Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)
    
                            if coluna==2:
    
                                coluna=0
    
                            else:
    
                                coluna+=1

        else:

            if item in  df_alternativos['Roteiro'].unique().tolist():
    
                df_ref_1 = df_alternativos[df_alternativos['Roteiro']==item].reset_index(drop=True)
    
                horario_inicial_voo = df_ref_1['Horario Voo'].min()
    
                horario_final_voo = df_ref_1['Horario Voo'].max()
    
                if horario_inicial_voo == horario_final_voo:
    
                    titulo_voos = f'{horario_inicial_voo}'
    
                else:
    
                    titulo_voos = f'{horario_inicial_voo} às {horario_final_voo}'

                lista_nome_voos = df_ref_1['Voo'].unique().tolist()

                voos_unidos = ' + '.join(lista_nome_voos)
    
                for carro in df_ref_1['Carros'].unique().tolist():
    
                    df_ref_2 = df_ref_1[df_ref_1['Carros']==carro].reset_index(drop=True)
    
                    modo = df_ref_2.at[0, 'Modo do Servico']
    
                    paxs_total = int(df_ref_2['Total ADT | CHD'].sum())
    
                    if modo=='REGULAR':
    
                        titulo_roteiro = f'Opção Alternativa | Roteiro {item}'
    
                        titulo_carro = f'Veículo {carro}'
    
                        titulo_modo_voo_pax = f'*{modo.title()} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'
    
                    else:
    
                        reserva = df_ref_2.at[0, 'Reserva']
    
                        titulo_roteiro = f'Opção Alternativa | Roteiro {item}'
    
                        titulo_carro = f'Veículo {carro}'
    
                        titulo_modo_voo_pax = f'*{modo.title()} | {reserva} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'
    
                    lista_apoios = df_ref_2['Apoios'].unique().tolist()
    
                    if 'X' in lista_apoios:
    
                        df_ref_3 = df_ref_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first', 'Apoios': 'first'})\
                            .sort_values(by='Data Horario Apresentacao').reset_index()
                    else:
    
                        df_ref_3 = df_ref_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first'})\
                            .sort_values(by='Data Horario Apresentacao').reset_index()
                
                    with row3[coluna]:
    
                        container = st.container(border=True, height=500)
    
                        container.header(titulo_roteiro)
    
                        container.subheader(titulo_carro)
    
                        container.markdown(titulo_modo_voo_pax)
    
                        if 'X' in lista_apoios:
    
                            container.dataframe(df_ref_3[['Apoios', 'Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)
    
                        else:
    
                            container.dataframe(df_ref_3[['Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)
    
                        if coluna==2:
    
                            coluna=0
    
                        else:
    
                            coluna+=1
    
                    df_ref_apoio = df_apoios_alternativos[(df_apoios_alternativos['Roteiro']==item) & 
                                                                    (df_apoios_alternativos['Carros']==carro)].reset_index(drop=True)
    
                    if len(df_ref_apoio)>0:
    
                        for carro_2 in df_ref_apoio['Carros Apoios'].unique().tolist():
    
                            df_ref_apoio_2 = df_ref_apoio[df_ref_apoio['Carros Apoios']==carro_2].reset_index(drop=True)
    
                            paxs_total = int(df_ref_apoio_2['Total ADT | CHD'].sum())
    
                            titulo_roteiro = f'Apoio | Opção Alternativa | Roteiro {item}'
    
                            titulo_carro_principal = f'Veículo Principal {carro}'
    
                            titulo_carro = f'Veículo {carro_2}'
    
                            titulo_modo_voo_pax = f'*{modo.title()} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'
    
                            df_ref_apoio_3 = df_ref_apoio_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first'})\
                                .sort_values(by='Data Horario Apresentacao').reset_index()
                            
                            with row3[coluna]:
    
                                container = st.container(border=True, height=500)
    
                                container.header(titulo_roteiro)
    
                                container.subheader(titulo_carro_principal)
    
                                container.subheader(titulo_carro)
    
                                container.markdown(titulo_modo_voo_pax)
    
                                container.dataframe(df_ref_apoio_3[['Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)
    
                                if coluna==2:
    
                                    coluna=0
    
                                else:
    
                                    coluna+=1

    return coluna

def definir_html(df_ref):

    if 'Data Horario Apresentacao' in df_ref.columns:
        
        df_ref = df_ref.sort_values(by='Data Horario Apresentacao').reset_index(drop=True)

    html=df_ref.to_html(index=False)

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                text-align: center;  /* Centraliza o texto */
            }}
            table {{
                margin: 0 auto;  /* Centraliza a tabela */
                border-collapse: collapse;  /* Remove espaço entre as bordas da tabela */
            }}
            th, td {{
                padding: 8px;  /* Adiciona espaço ao redor do texto nas células */
                border: 1px solid black;  /* Adiciona bordas às células */
                text-align: center;
            }}
        </style>
    </head>
    <body>
        {html}
    </body>
    </html>
    """

    return html

def criar_output_html(nome_html, html):

    with open(nome_html, "w", encoding="utf-8") as file:

        file.write(f'<p style="font-size:40px;">Junção de Voos</p>\n\n')
        
        file.write(html)

        file.write('\n\n\n')

        file.write(f'<p style="font-size:40px;">Roteiros</p>\n\n')

def inserir_roteiros_html(nome_html, df_pdf):

    roteiro = 0

    df_ref = df_pdf[['Roteiro', 'Carros', 'Horario Voo / Menor Horário']].drop_duplicates().reset_index(drop=True)

    for index in range(len(df_ref)):

        roteiro_ref = df_ref.at[index, 'Roteiro']

        carro_ref = df_ref.at[index, 'Carros']

        hv_ref = df_ref.at[index, 'Horario Voo / Menor Horário']

        df_ref_roteiro = df_pdf[(df_pdf['Roteiro']==roteiro_ref) & (df_pdf['Carros']==carro_ref) & 
                          (df_pdf['Horario Voo / Menor Horário']==hv_ref)].reset_index(drop=True)
        
        lista_nome_voos = df_ref_roteiro['Voo'].unique().tolist()

        voos_unidos = ' + '.join(lista_nome_voos)

        if carro_ref==1:

            roteiro+=1

        for carro in df_ref_roteiro['Carros'].unique().tolist():

            df_ref_carro = df_ref_roteiro[df_ref_roteiro['Carros']==carro]\
                [['Roteiro', 'Carros', 'Modo do Servico', 'Voo', 'Horario Voo', 'Junção', 'Est Origem', 'Total ADT | CHD', 
                'Data Horario Apresentacao']].reset_index(drop=True)
            
            total_paxs = df_ref_carro['Total ADT | CHD'].sum()
            
            html = definir_html(df_ref_carro)

            with open(nome_html, "a", encoding="utf-8") as file:

                file.write(f'<p style="font-size:30px;">Roteiro {roteiro} | Carro {carro} | {voos_unidos} | {int(total_paxs)} Paxs</p>\n\n')

                file.write(html)

                file.write('\n\n')

def verificar_rotas_alternativas_ou_plotar_roteiros(df_roteiros_alternativos, row_warning, row3, coluna, df_hoteis_pax_max, 
                                                    df_juncoes_pax_max, df_voos_pax_max, df_router_filtrado_2, df_roteiros_apoios, 
                                                    df_roteiros_apoios_alternativos, df_juncao_voos, nome_html):

    if len(df_roteiros_alternativos)>0:

        with row_warning[0]:

            st.warning('Existem opções alternativas para algumas rotas. Por favor, informe quais rotas alternativas serão usadas.')

    else:

        lista_dfs = [df_fretamentos, df_hoteis_pax_max, df_juncoes_pax_max, df_voos_pax_max, df_router_filtrado_2, df_roteiros_apoios]

        n_carros = 0

        for df in lista_dfs:
            
            if len(df)>0:

                n_carros += len(df[['Roteiro', 'Carros']].drop_duplicates())

        with row_warning[0]:

            st.header(f'A roteirização usou um total de {n_carros} carros')

        if len(df_hoteis_pax_max)>0:

            coluna = plotar_roteiros_simples(df_hoteis_pax_max, row3, coluna)

        if len(df_juncoes_pax_max)>0:

            coluna = plotar_roteiros_simples(df_juncoes_pax_max, row3, coluna)

        if len(df_voos_pax_max)>0:

            coluna = plotar_roteiros_simples(df_voos_pax_max, row3, coluna)

        coluna = plotar_roteiros_gerais(df_router_filtrado_2, df_roteiros_apoios, df_roteiros_alternativos, 
                                        df_roteiros_apoios_alternativos, coluna, row3)

        html = definir_html(df_juncao_voos)

        criar_output_html(nome_html, html)

        df_pdf = pd.concat([df_router_filtrado_2, df_fretamentos, df_hoteis_pax_max, df_juncoes_pax_max, df_voos_pax_max], 
                           ignore_index=True)
        
        for index in range(len(df_pdf)):

            tipo_de_servico_ref = df_pdf.at[index, 'Modo do Servico']

            juncao_ref_2 = df_pdf.at[index, 'Junção']

            if tipo_de_servico_ref == 'REGULAR' and not pd.isna(juncao_ref_2):

                df_pdf.at[index, 'Horario Voo / Menor Horário'] = df_pdf.at[index, 'Menor Horário']

            elif (tipo_de_servico_ref == 'REGULAR' and pd.isna(juncao_ref_2)) or (tipo_de_servico_ref != 'REGULAR'):

                df_pdf.at[index, 'Horario Voo / Menor Horário'] = df_pdf.at[index, 'Horario Voo']

        df_pdf = df_pdf.sort_values(by=['Horario Voo / Menor Horário', 'Junção']).reset_index(drop=True)

        inserir_roteiros_html(nome_html, df_pdf)

        with open(nome_html, "r", encoding="utf-8") as file:

            html_content = file.read()

        st.download_button(
            label="Baixar Arquivo HTML",
            data=html_content,
            file_name=nome_html,
            mime="text/html"
        )

def plotar_roteiros_gerais_alternativos(df_servicos, df_apoios, df_alternativos, df_alternativos_2, df_apoios_alternativos, 
                                        df_apoios_alternativos_2, coluna, row3):

    for item in df_alternativos['Roteiro'].unique().tolist():

        df_ref_1 = df_servicos[df_servicos['Roteiro']==item].reset_index(drop=True)

        horario_inicial_voo = df_ref_1['Horario Voo'].min()

        horario_final_voo = df_ref_1['Horario Voo'].max()

        if horario_inicial_voo == horario_final_voo:

            titulo_voos = f'{horario_inicial_voo}'

        else:

            titulo_voos = f'{horario_inicial_voo} às {horario_final_voo}'

        lista_nome_voos = df_ref_1['Voo'].unique().tolist()

        voos_unidos = ' + '.join(lista_nome_voos)

        for carro in df_ref_1['Carros'].unique().tolist():

            df_ref_2 = df_ref_1[df_ref_1['Carros']==carro].reset_index(drop=True)

            modo = df_ref_2.at[0, 'Modo do Servico']

            paxs_total = int(df_ref_2['Total ADT | CHD'].sum())

            if modo=='REGULAR':

                titulo_roteiro = f'Roteiro {item}'

                titulo_carro = f'Veículo {carro}'

                titulo_modo_voo_pax = f'*{modo.title()} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'

            else:

                reserva = df_ref_2.at[0, 'Reserva']

                titulo_roteiro = f'Roteiro {item}'

                titulo_carro = f'Veículo {carro}'

                titulo_modo_voo_pax = f'*{modo.title()} | {reserva} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'

            lista_apoios = df_ref_2['Apoios'].unique().tolist()

            if 'X' in lista_apoios:

                df_ref_3 = df_ref_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first', 'Apoios': 'first'})\
                    .sort_values(by='Data Horario Apresentacao').reset_index()
            else:

                df_ref_3 = df_ref_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first'})\
                    .sort_values(by='Data Horario Apresentacao').reset_index()
        
            with row3[coluna]:

                container = st.container(border=True, height=500)

                container.header(titulo_roteiro)

                container.subheader(titulo_carro)

                container.markdown(titulo_modo_voo_pax)

                if 'X' in lista_apoios:

                    container.dataframe(df_ref_3[['Apoios', 'Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)

                else:

                    container.dataframe(df_ref_3[['Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)

                if coluna==2:

                    coluna=0

                else:

                    coluna+=1

            df_ref_apoio = df_apoios[(df_apoios['Roteiro']==item) & (df_apoios['Carros']==carro)].reset_index(drop=True)

            if len(df_ref_apoio)>0:

                for carro_2 in df_ref_apoio['Carros Apoios'].unique().tolist():

                    df_ref_apoio_2 = df_ref_apoio[df_ref_apoio['Carros Apoios']==carro_2].reset_index(drop=True)

                    paxs_total = int(df_ref_apoio_2['Total ADT | CHD'].sum())

                    titulo_roteiro = f'Apoio | Roteiro {item}'

                    titulo_carro_principal = f'Veículo Principal {carro}'

                    titulo_carro = f'Veículo Apoio {carro_2}'

                    titulo_modo_voo_pax = f'*{modo.title()} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'

                    df_ref_apoio_3 = df_ref_apoio_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first'})\
                        .sort_values(by='Data Horario Apresentacao').reset_index()
                    
                    with row3[coluna]:

                        container = st.container(border=True, height=500)

                        container.header(titulo_roteiro)

                        container.subheader(titulo_carro_principal)

                        container.subheader(titulo_carro)

                        container.markdown(titulo_modo_voo_pax)

                        container.dataframe(df_ref_apoio_3[['Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)

                        if coluna==2:

                            coluna=0

                        else:

                            coluna+=1

        if item in  df_alternativos['Roteiro'].unique().tolist():

            df_ref_1 = df_alternativos[df_alternativos['Roteiro']==item].reset_index(drop=True)

            horario_inicial_voo = df_ref_1['Horario Voo'].min()

            horario_final_voo = df_ref_1['Horario Voo'].max()

            if horario_inicial_voo == horario_final_voo:

                titulo_voos = f'{horario_inicial_voo}'

            else:

                titulo_voos = f'{horario_inicial_voo} às {horario_final_voo}'

            lista_nome_voos = df_ref_1['Voo'].unique().tolist()

            voos_unidos = ' + '.join(lista_nome_voos)

            for carro in df_ref_1['Carros'].unique().tolist():

                df_ref_2 = df_ref_1[df_ref_1['Carros']==carro].reset_index(drop=True)

                modo = df_ref_2.at[0, 'Modo do Servico']

                paxs_total = int(df_ref_2['Total ADT | CHD'].sum())

                if modo=='REGULAR':

                    titulo_roteiro = f'Opção Alternativa | Roteiro {item}'

                    titulo_carro = f'Veículo {carro}'

                    titulo_modo_voo_pax = f'*{modo.title()} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'

                else:

                    reserva = df_ref_2.at[0, 'Reserva']

                    titulo_roteiro = f'Opção Alternativa | Roteiro {item}'

                    titulo_carro = f'Veículo {carro}'

                    titulo_modo_voo_pax = f'*{modo.title()} | {reserva} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'

                lista_apoios = df_ref_2['Apoios'].unique().tolist()

                if 'X' in lista_apoios:

                    df_ref_3 = df_ref_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first', 'Apoios': 'first'})\
                        .sort_values(by='Data Horario Apresentacao').reset_index()
                else:

                    df_ref_3 = df_ref_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first'})\
                        .sort_values(by='Data Horario Apresentacao').reset_index()
            
                with row3[coluna]:

                    container = st.container(border=True, height=500)

                    container.header(titulo_roteiro)

                    container.subheader(titulo_carro)

                    container.markdown(titulo_modo_voo_pax)

                    if 'X' in lista_apoios:

                        container.dataframe(df_ref_3[['Apoios', 'Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)

                    else:

                        container.dataframe(df_ref_3[['Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)

                    if coluna==2:

                        coluna=0

                    else:

                        coluna+=1

                df_ref_apoio = df_apoios_alternativos[(df_apoios_alternativos['Roteiro']==item) & 
                                                                (df_apoios_alternativos['Carros']==carro)].reset_index(drop=True)

                if len(df_ref_apoio)>0:

                    for carro_2 in df_ref_apoio['Carros Apoios'].unique().tolist():

                        df_ref_apoio_2 = df_ref_apoio[df_ref_apoio['Carros Apoios']==carro_2].reset_index(drop=True)

                        paxs_total = int(df_ref_apoio_2['Total ADT | CHD'].sum())

                        titulo_roteiro = f'Apoio | Opção Alternativa | Roteiro {item}'

                        titulo_carro_principal = f'Veículo Principal {carro}'

                        titulo_carro = f'Veículo {carro_2}'

                        titulo_modo_voo_pax = f'*{modo.title()} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'

                        df_ref_apoio_3 = df_ref_apoio_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first'})\
                            .sort_values(by='Data Horario Apresentacao').reset_index()
                        
                        with row3[coluna]:

                            container = st.container(border=True, height=500)

                            container.header(titulo_roteiro)

                            container.subheader(titulo_carro_principal)

                            container.subheader(titulo_carro)

                            container.markdown(titulo_modo_voo_pax)

                            container.dataframe(df_ref_apoio_3[['Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)

                            if coluna==2:

                                coluna=0

                            else:

                                coluna+=1

        if item in  df_alternativos_2['Roteiro'].unique().tolist():

            df_ref_1 = df_alternativos_2[df_alternativos_2['Roteiro']==item].reset_index(drop=True)

            horario_inicial_voo = df_ref_1['Horario Voo'].min()

            horario_final_voo = df_ref_1['Horario Voo'].max()

            if horario_inicial_voo == horario_final_voo:

                titulo_voos = f'{horario_inicial_voo}'

            else:

                titulo_voos = f'{horario_inicial_voo} às {horario_final_voo}'

            lista_nome_voos = df_ref_1['Voo'].unique().tolist()

            voos_unidos = ' + '.join(lista_nome_voos)

            for carro in df_ref_1['Carros'].unique().tolist():

                df_ref_2 = df_ref_1[df_ref_1['Carros']==carro].reset_index(drop=True)

                modo = df_ref_2.at[0, 'Modo do Servico']

                paxs_total = int(df_ref_2['Total ADT | CHD'].sum())

                if modo=='REGULAR':

                    titulo_roteiro = f'Opção Alternativa 2 | Roteiro {item}'

                    titulo_carro = f'Veículo {carro}'

                    titulo_modo_voo_pax = f'*{modo.title()} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'

                else:

                    reserva = df_ref_2.at[0, 'Reserva']

                    titulo_roteiro = f'Opção Alternativa 2 | Roteiro {item}'

                    titulo_carro = f'Veículo {carro}'

                    titulo_modo_voo_pax = f'*{modo.title()} | {reserva} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'

                lista_apoios = df_ref_2['Apoios'].unique().tolist()

                if 'X' in lista_apoios:

                    df_ref_3 = df_ref_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first', 'Apoios': 'first'})\
                        .sort_values(by='Data Horario Apresentacao').reset_index()
                else:

                    df_ref_3 = df_ref_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first'})\
                        .sort_values(by='Data Horario Apresentacao').reset_index()
            
                with row3[coluna]:

                    container = st.container(border=True, height=500)

                    container.header(titulo_roteiro)

                    container.subheader(titulo_carro)

                    container.markdown(titulo_modo_voo_pax)

                    if 'X' in lista_apoios:

                        container.dataframe(df_ref_3[['Apoios', 'Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)

                    else:

                        container.dataframe(df_ref_3[['Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)

                    if coluna==2:

                        coluna=0

                    else:

                        coluna+=1

                df_ref_apoio = df_apoios_alternativos_2[(df_apoios_alternativos_2['Roteiro']==item) & 
                                                                (df_apoios_alternativos_2['Carros']==carro)].reset_index(drop=True)

                if len(df_ref_apoio)>0:

                    for carro_2 in df_ref_apoio['Carros Apoios'].unique().tolist():

                        df_ref_apoio_2 = df_ref_apoio[df_ref_apoio['Carros Apoios']==carro_2].reset_index(drop=True)

                        paxs_total = int(df_ref_apoio_2['Total ADT | CHD'].sum())

                        titulo_roteiro = f'Apoio | Opção Alternativa 2 | Roteiro {item}'

                        titulo_carro_principal = f'Veículo Principal {carro}'

                        titulo_carro = f'Veículo {carro_2}'

                        titulo_modo_voo_pax = f'*{modo.title()} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'

                        df_ref_apoio_3 = df_ref_apoio_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first'})\
                            .sort_values(by='Data Horario Apresentacao').reset_index()
                        
                        with row3[coluna]:

                            container = st.container(border=True, height=500)

                            container.header(titulo_roteiro)

                            container.subheader(titulo_carro_principal)

                            container.subheader(titulo_carro)

                            container.markdown(titulo_modo_voo_pax)

                            container.dataframe(df_ref_apoio_3[['Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)

                            if coluna==2:

                                coluna=0

                            else:

                                coluna+=1

    return coluna

def plotar_roteiros_gerais_final(df_servicos, df_apoios, df_alternativos, df_apoios_alternativos, coluna):

    lista_roteiros = df_servicos['Roteiro'].unique().tolist()

    lista_roteiros.extend(df_alternativos['Roteiro'].unique().tolist())

    lista_roteiros = sorted(lista_roteiros)

    for item in lista_roteiros:

        if not item in df_alternativos['Roteiro'].unique().tolist():

            df_ref_1 = df_servicos[df_servicos['Roteiro']==item].reset_index(drop=True)
    
            horario_inicial_voo = df_ref_1['Horario Voo'].min()
    
            horario_final_voo = df_ref_1['Horario Voo'].max()
    
            if horario_inicial_voo == horario_final_voo:
    
                titulo_voos = f'{horario_inicial_voo}'
    
            else:
    
                titulo_voos = f'{horario_inicial_voo} às {horario_final_voo}'

            lista_nome_voos = df_ref_1['Voo'].unique().tolist()

            voos_unidos = ' + '.join(lista_nome_voos)
    
            for carro in df_ref_1['Carros'].unique().tolist():
    
                df_ref_2 = df_ref_1[df_ref_1['Carros']==carro].reset_index(drop=True)
    
                modo = df_ref_2.at[0, 'Modo do Servico']
    
                paxs_total = int(df_ref_2['Total ADT | CHD'].sum())
    
                if modo=='REGULAR':
    
                    titulo_roteiro = f'Roteiro {item}'
    
                    titulo_carro = f'Veículo {carro}'
    
                    titulo_modo_voo_pax = f'*{modo.title()} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'
    
                else:
    
                    reserva = df_ref_2.at[0, 'Reserva']
    
                    titulo_roteiro = f'Roteiro {item}'
    
                    titulo_carro = f'Veículo {carro}'
    
                    titulo_modo_voo_pax = f'*{modo.title()} | {reserva} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'
    
                lista_apoios = df_ref_2['Apoios'].unique().tolist()
    
                if 'X' in lista_apoios:
    
                    df_ref_3 = df_ref_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first', 'Apoios': 'first'})\
                        .sort_values(by='Data Horario Apresentacao').reset_index()
                else:
    
                    df_ref_3 = df_ref_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first'})\
                        .sort_values(by='Data Horario Apresentacao').reset_index()
            
                with row3[coluna]:
    
                    container = st.container(border=True, height=500)
    
                    container.header(titulo_roteiro)
    
                    container.subheader(titulo_carro)
    
                    container.markdown(titulo_modo_voo_pax)
    
                    if 'X' in lista_apoios:
    
                        container.dataframe(df_ref_3[['Apoios', 'Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)
    
                    else:
    
                        container.dataframe(df_ref_3[['Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)
    
                    if coluna==2:
    
                        coluna=0
    
                    else:
    
                        coluna+=1
    
                df_ref_apoio = df_apoios[(df_apoios['Roteiro']==item) & (df_apoios['Carros']==carro)].reset_index(drop=True)
    
                if len(df_ref_apoio)>0:
    
                    for carro_2 in df_ref_apoio['Carros Apoios'].unique().tolist():
    
                        df_ref_apoio_2 = df_ref_apoio[df_ref_apoio['Carros Apoios']==carro_2].reset_index(drop=True)
    
                        paxs_total = int(df_ref_apoio_2['Total ADT | CHD'].sum())
    
                        titulo_roteiro = f'Apoio | Roteiro {item}'
    
                        titulo_carro_principal = f'Veículo Principal {carro}'
    
                        titulo_carro = f'Veículo Apoio {carro_2}'
    
                        titulo_modo_voo_pax = f'*{modo.title()} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'
    
                        df_ref_apoio_3 = df_ref_apoio_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first'})\
                            .sort_values(by='Data Horario Apresentacao').reset_index()
                        
                        with row3[coluna]:
    
                            container = st.container(border=True, height=500)
    
                            container.header(titulo_roteiro)
    
                            container.subheader(titulo_carro_principal)
    
                            container.subheader(titulo_carro)
    
                            container.markdown(titulo_modo_voo_pax)
    
                            container.dataframe(df_ref_apoio_3[['Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)
    
                            if coluna==2:
    
                                coluna=0
    
                            else:
    
                                coluna+=1

        else:

            if item in  df_alternativos['Roteiro'].unique().tolist():
    
                df_ref_1 = df_alternativos[df_alternativos['Roteiro']==item].reset_index(drop=True)
    
                horario_inicial_voo = df_ref_1['Horario Voo'].min()
    
                horario_final_voo = df_ref_1['Horario Voo'].max()
    
                if horario_inicial_voo == horario_final_voo:
    
                    titulo_voos = f'{horario_inicial_voo}'
    
                else:
    
                    titulo_voos = f'{horario_inicial_voo} às {horario_final_voo}'

                lista_nome_voos = df_ref_1['Voo'].unique().tolist()

                voos_unidos = ' + '.join(lista_nome_voos)
    
                for carro in df_ref_1['Carros'].unique().tolist():
    
                    df_ref_2 = df_ref_1[df_ref_1['Carros']==carro].reset_index(drop=True)
    
                    modo = df_ref_2.at[0, 'Modo do Servico']
    
                    paxs_total = int(df_ref_2['Total ADT | CHD'].sum())
    
                    if modo=='REGULAR':
    
                        titulo_roteiro = f'Opção Alternativa | Roteiro {item}'
    
                        titulo_carro = f'Veículo {carro}'
    
                        titulo_modo_voo_pax = f'*{modo.title()} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'
    
                    else:
    
                        reserva = df_ref_2.at[0, 'Reserva']
    
                        titulo_roteiro = f'Opção Alternativa | Roteiro {item}'
    
                        titulo_carro = f'Veículo {carro}'
    
                        titulo_modo_voo_pax = f'*{modo.title()} | {reserva} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'
    
                    lista_apoios = df_ref_2['Apoios'].unique().tolist()
    
                    if 'X' in lista_apoios:
    
                        df_ref_3 = df_ref_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first', 'Apoios': 'first'})\
                            .sort_values(by='Data Horario Apresentacao').reset_index()
                    else:
    
                        df_ref_3 = df_ref_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first'})\
                            .sort_values(by='Data Horario Apresentacao').reset_index()
                
                    with row3[coluna]:
    
                        container = st.container(border=True, height=500)
    
                        container.header(titulo_roteiro)
    
                        container.subheader(titulo_carro)
    
                        container.markdown(titulo_modo_voo_pax)
    
                        if 'X' in lista_apoios:
    
                            container.dataframe(df_ref_3[['Apoios', 'Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)
    
                        else:
    
                            container.dataframe(df_ref_3[['Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)
    
                        if coluna==2:
    
                            coluna=0
    
                        else:
    
                            coluna+=1
    
                    df_ref_apoio = df_apoios_alternativos[(df_apoios_alternativos['Roteiro']==item) & 
                                                                    (df_apoios_alternativos['Carros']==carro)].reset_index(drop=True)
    
                    if len(df_ref_apoio)>0:
    
                        for carro_2 in df_ref_apoio['Carros Apoios'].unique().tolist():
    
                            df_ref_apoio_2 = df_ref_apoio[df_ref_apoio['Carros Apoios']==carro_2].reset_index(drop=True)
    
                            paxs_total = int(df_ref_apoio_2['Total ADT | CHD'].sum())
    
                            titulo_roteiro = f'Apoio | Opção Alternativa | Roteiro {item}'
    
                            titulo_carro_principal = f'Veículo Principal {carro}'
    
                            titulo_carro = f'Veículo {carro_2}'
    
                            titulo_modo_voo_pax = f'*{modo.title()} | {voos_unidos} | {titulo_voos} | {paxs_total} paxs*'
    
                            df_ref_apoio_3 = df_ref_apoio_2.groupby('Est Origem').agg({'Total ADT | CHD': 'sum', 'Data Horario Apresentacao': 'first'})\
                                .sort_values(by='Data Horario Apresentacao').reset_index()
                            
                            with row3[coluna]:
    
                                container = st.container(border=True, height=500)
    
                                container.header(titulo_roteiro)
    
                                container.subheader(titulo_carro_principal)
    
                                container.subheader(titulo_carro)
    
                                container.markdown(titulo_modo_voo_pax)
    
                                container.dataframe(df_ref_apoio_3[['Est Origem', 'Total ADT | CHD', 'Data Horario Apresentacao']], hide_index=True)
    
                                if coluna==2:
    
                                    coluna=0
    
                                else:
    
                                    coluna+=1

    return coluna

def verificar_exclusivo(observacao):

    observacao_upper = str(observacao).upper()

    pattern = r"E.*X.*C.*L.*U.*S.*I.*V.*O"
    
    if re.search(pattern, observacao_upper):
        return True
    return False

st.set_page_config(layout='wide')

st.title('Roteirizador de Transfer Out - Maceió')

st.divider()

st.header('Robô')

st.markdown('*se nenhum robô for escolhido, o padrão é roteirizar com Jarbas*')

row0 = st.columns(2)

with row0[0]:

    robo_usado = st.radio('Escolha o robô para roteirizar', ['Jarbas', 'Gerald'], index=None)

    if robo_usado=='Gerald':

        pax_max_gerald = st.number_input('Máximo de Paxs por Carro', step=1, value=30, key='pax_max_gerald')

    container_jarbas = st.container(border=True)

    container_jarbas.subheader('Jarbas')

    container_jarbas.write('Jarbas vai gerar os roteiros priorizando apenas a sequência de hoteis. ' + \
                           'Mais indicado pra quando não existe limitação de carros na frota.')

with row0[1]:

    container_gerald = st.container(border=True)

    container_gerald.subheader('Gerald')

    container_gerald.write('Gerald, vai gerar os roteiros tentando otimizar as rotas em carros maiores.' + 
                           ' Se lotar carros com uma determinada capacidade for de boa utilidade, melhor usar Gerald. E se o usar,' + 
                           ' precisa informar qual a capacidade máxima do veículo que ele deve tentar lotar quando roteirizar.')

st.divider()

st.header('Parâmetros')

if not 'df_router' in st.session_state:

    st.session_state.df_router = gerar_df_phoenix('vw_router')

    st.session_state.df_router = st.session_state.df_router[st.session_state.df_router['Voo']!='AD - 0001']\
        .reset_index(drop=True)

    st.session_state.lista_voos = st.session_state.df_router[~(pd.isna(st.session_state.df_router['Voo'])) & 
                                                                (st.session_state.df_router['Tipo de Servico']=='OUT') & 
                                                                (st.session_state.df_router['Status do Servico']!='CANCELADO')]\
                                                                    ['Voo'].unique().tolist()
    
    st.session_state.vw_payment_guide = gerar_df_phoenix('vw_payment_guide')

if not 'df_grande_maceio' in st.session_state:

    puxar_sequencias_hoteis()

    st.session_state.dict_regioes_hoteis = \
        {'OUT - ORLA DE MACEIÓ (OU PRÓXIMOS) ': ['df_orla_maceio', 'Orla Maceio', 'Hoteis Orla Maceio', 'Orla Maceió'], 
         'OUT - GRANDE MACEIÓ': ['df_grande_maceio', 'Grande Maceio', 'Hoteis Grande Maceio', 'Grande Maceió'], 
         'OUT - BARRA DE SÃO MIGUEL': ['df_sao_miguel', 'Sao Miguel', 'Hoteis Sao Miguel', 'São Miguel'], 
         'OUT- FRANCÊS': ['df_frances', 'Frances', 'Hoteis Frances', 'Francês'], 
         'OUT - MARAGOGI / JAPARATINGA': ['df_maragogi', 'Maragogi', 'Hoteis Maragogi', 'Maragogi'], 
         'OUT - SÃO MIGUEL DOS MILAGRES ': ['df_milagres', 'Milagres', 'Hoteis Milagres', 'Milagres'], 
         'OUT - BARRA DE SANTO ANTÔNIO': ['df_santo_antonio', 'Santo Antonio', 'Hoteis Santo Antonio', 'Santo Antônio'], 
         'OUT - PORTO DE GALINHAS': ['df_porto', 'Porto', 'Hoteis Porto', 'Porto']}

row1 = st.columns(3)

with row1[0]:

    intervalo_inicial_orla_maceio = objeto_intervalo('Horário Último Hotel | Orla Maceió', datetime.time(3, 0), 
                                                     'intervalo_inicial_orla_maceio')
    
    intervalo_inicial_grande_maceio = objeto_intervalo('Horário Último Hotel | Grande Maceió, Francês e Barra de São Miguel', 
                                                       datetime.time(3, 30), 'intervalo_inicial_grande_maceio')
    
    intervalo_hoteis_bairros_iguais = objeto_intervalo('Intervalo Entre Hoteis de Mesmo Bairro', datetime.time(0, 5), 
                                                       'intervalo_hoteis_bairros_iguais')

    intervalo_hoteis_bairros_diferentes = objeto_intervalo('Intervalo Entre Hoteis de Bairros Diferentes', datetime.time(0, 10), 
                                                           'intervalo_hoteis_bairros_diferentes')

with row1[1]:

    intervalo_inicial_maragogi = objeto_intervalo('Horário Último Hotel | Maragogi e Milagres', datetime.time(5, 0), 
                                                  'intervalo_inicial_maragogi')
    
    intervalo_inicial_santo_antonio = objeto_intervalo('Horário Último Hotel | Santo Antônio', datetime.time(4, 0), 
                                                       'intervalo_inicial_santo_antonio')
    
    pax_max = st.number_input('Máximo de Paxs por Carro', step=1, value=46, key='pax_max')

    voos_fret = st.multiselect('Voos Fretamento', sorted(st.session_state.lista_voos), default='G3 - 9753')
 
with row1[2]:

    intervalo_inicial_porto = objeto_intervalo('Horário Último Hotel | Porto', datetime.time(7, 0), 'intervalo_inicial_porto')

    intervalo_pu_hotel = objeto_intervalo('Intervalo Hoteis | Primeiro vs Último', datetime.time(0, 40), 'intervalo_pu_hotel')

    max_hoteis = st.number_input('Máximo de Hoteis por Carro', step=1, value=8, key='max_hoteis')

    pax_cinco_min = st.number_input('Paxs Extras - Adição de 5 minutos', step=1, value=15, key='pax_cinco_min')

st.divider()

st.header('Juntar Voos')

if 'df_juncao_voos' not in st.session_state:

    st.session_state.df_juncao_voos = pd.DataFrame(columns=['Servico', 'Voo', 'Horário', 'Junção'])

row2 = st.columns(3)

# Botões Atualizar Hoteis, Atualizar Dados Phoenix, campos de Data e botões de roteirizar e visualizar voos

with row2[0]:

    row2_1=st.columns(2)

    # Botão Atualizar Hoteis

    with row2_1[0]:

        atualizar_hoteis = st.button('Atualizar Sequência de Hoteis')

        # Puxando sequência de hoteis

        if atualizar_hoteis:

            puxar_sequencias_hoteis()

            st.session_state.dict_regioes_hoteis = \
                {'OUT - ORLA DE MACEIÓ (OU PRÓXIMOS) ': ['df_orla_maceio', 'Orla Maceio', 'Hoteis Orla Maceio', 'Orla Maceió'], 
                'OUT - GRANDE MACEIÓ': ['df_grande_maceio', 'Grande Maceio', 'Hoteis Grande Maceio', 'Grande Maceió'], 
                'OUT - BARRA DE SÃO MIGUEL': ['df_sao_miguel', 'Sao Miguel', 'Hoteis Sao Miguel', 'São Miguel'], 
                'OUT- FRANCÊS': ['df_frances', 'Frances', 'Hoteis Frances', 'Francês'], 
                'OUT - MARAGOGI / JAPARATINGA': ['df_maragogi', 'Maragogi', 'Hoteis Maragogi', 'Maragogi'], 
                'OUT - SÃO MIGUEL DOS MILAGRES ': ['df_milagres', 'Milagres', 'Hoteis Milagres', 'Milagres'], 
                'OUT - BARRA DE SANTO ANTÔNIO': ['df_santo_antonio', 'Santo Antonio', 'Hoteis Santo Antonio', 'Santo Antônio'], 
                'OUT - PORTO DE GALINHAS': ['df_porto', 'Porto', 'Hoteis Porto', 'Porto']}

    # Botão Atualizar Dados Phoenix

    with row2_1[1]:

        atualizar_phoenix = st.button('Atualizar Dados Phoenix')

        if atualizar_phoenix:

            st.session_state.df_router = gerar_df_phoenix('vw_router')

            st.session_state.df_router = st.session_state.df_router[st.session_state.df_router['Voo']!='AD - 0001']\
                .reset_index(drop=True)

            st.session_state.lista_voos = st.session_state.df_router[~(pd.isna(st.session_state.df_router['Voo'])) & 
                                                                     (st.session_state.df_router['Tipo de Servico']=='OUT') & 
                                                                     (st.session_state.df_router['Status do Servico']!='CANCELADO')]\
                                                                        ['Voo'].unique().tolist()
            
            st.session_state.vw_payment_guide = gerar_df_phoenix('vw_payment_guide')

    # Campo de data

    container_roteirizar = st.container(border=True)

    data_roteiro = container_roteirizar.date_input('Data do Roteiro', value=None, format='DD/MM/YYYY', key='data_roteiro')

    df_router_data_roteiro = st.session_state.df_router[(st.session_state.df_router['Data Execucao']==data_roteiro) & 
                                                        (st.session_state.df_router['Tipo de Servico']=='OUT') & 
                                                        (st.session_state.df_router['Status do Servico']!='CANCELADO')]\
                                                            .reset_index(drop=True)

    lista_servicos = df_router_data_roteiro['Servico'].unique().tolist()

    servico_roteiro = container_roteirizar.selectbox('Serviço', lista_servicos, index=None, placeholder='Escolha um Serviço', 
                                                     key='servico_roteiro')  

    row_container = container_roteirizar.columns(2)

    # Botão roteirizar

    with row_container[0]:

        roteirizar = st.button('Roteirizar')

    # Botão Visualizar Voos

    with row_container[1]:

        visualizar_voos = st.button('Visualizar Voos')

# Gerar dataframe com os voos da data selecionada e imprimir na tela o dataframe

if visualizar_voos and servico_roteiro:

    df_router_filtrado = st.session_state.df_router[(st.session_state.df_router['Data Execucao']==data_roteiro) & 
                                                    (st.session_state.df_router['Tipo de Servico']=='OUT') & 
                                                    (st.session_state.df_router['Status do Servico']!='CANCELADO') & 
                                                    (st.session_state.df_router['Servico']==servico_roteiro)]\
                                                        .reset_index(drop=True)
    
    st.session_state.df_servico_voos_horarios = df_router_filtrado[['Servico', 'Voo', 'Horario Voo']]\
    .sort_values(by=['Horario Voo']).drop_duplicates().reset_index(drop=True)
    
    st.session_state.df_servico_voos_horarios['Horario Voo'] = pd.to_datetime(st.session_state.df_servico_voos_horarios['Horario Voo'], 
                                                                              format='%H:%M:%S').dt.time
    
if servico_roteiro and 'df_servico_voos_horarios' in st.session_state:

    with row2[0]:

        st.dataframe(st.session_state.df_servico_voos_horarios, hide_index=True) 

# Formulário de Junção de Voos

with row2[1]:

    with st.form('juntar_voos_form_novo'):

        # Captando intervalo entre voos

        horario_inicial = st.time_input('Horário Inicial Voo', value=None, key='horario_inicial', step=300)

        horario_final = st.time_input('Horário Final Voo', value=None, key='horario_final', step=300)

        # Filtrando dataframe por Horario Voo e Servico

        if horario_inicial and horario_final and servico_roteiro:

            df_voos_hi_hf = st.session_state.df_servico_voos_horarios\
                [(st.session_state.df_servico_voos_horarios['Horario Voo']>=horario_inicial) & 
                 (st.session_state.df_servico_voos_horarios['Horario Voo']<=horario_final) & 
                 (st.session_state.df_servico_voos_horarios['Servico']==servico_roteiro)]\
                    [['Servico', 'Voo', 'Horario Voo']].reset_index(drop=True)
            
            df_voos_hi_hf = df_voos_hi_hf.rename(columns={'Horario Voo': 'Horário'})
        
            if len(st.session_state.df_juncao_voos)>0:

                juncao_max = st.session_state.df_juncao_voos['Junção'].max()

                df_voos_hi_hf['Junção'] = juncao_max+1

            else:

                df_voos_hi_hf['Junção'] = 1      

        lancar_juncao = st.form_submit_button('Lançar Junção')

        # Lançando junção

        if lancar_juncao:

            st.session_state.df_juncao_voos = pd.concat([st.session_state.df_juncao_voos, df_voos_hi_hf], ignore_index=True)

# Botões pra limpar junções

with row2[2]:

    row2_1 = st.columns(2)

    # Limpar todas as junções

    with row2_1[0]:

        limpar_juncoes = st.button('Limpar Todas as Junções')

    # Limpar junções específicas

    with row2_1[1]:

        limpar_juncao_esp = st.button('Limpar Junção Específica')

        juncao_limpar = st.number_input('Junção', step=1, value=None, key='juncao_limpar')

    # Se for pra limpar todas as junções

    if limpar_juncoes:

        voo=None

        st.session_state.df_juncao_voos = pd.DataFrame(columns=['Servico', 'Voo', 'Horário', 'Junção'])

    # Se for limpar junções específicas

    if limpar_juncao_esp and juncao_limpar==1: # se a exclusão for da junção 1

        st.session_state.df_juncao_voos = st.session_state.df_juncao_voos[st.session_state.df_juncao_voos['Junção']!=juncao_limpar]\
        .reset_index(drop=True)

        for index, value in st.session_state.df_juncao_voos['Junção'].items():

            st.session_state.df_juncao_voos.at[index, 'Junção']-=1

    elif limpar_juncao_esp and juncao_limpar: # se a exclusão não for da junção 1

        st.session_state.df_juncao_voos = st.session_state.df_juncao_voos[st.session_state.df_juncao_voos['Junção']!=juncao_limpar].reset_index(drop=True)

        juncao_ref=1

        for juncao in st.session_state.df_juncao_voos['Junção'].unique().tolist():

            if juncao>1:

                juncao_ref+=1

                st.session_state.df_juncao_voos.loc[st.session_state.df_juncao_voos['Junção']==juncao, 'Junção']=juncao_ref   

    container_df_juncao_voos = st.container()     

    container_df_juncao_voos.dataframe(st.session_state.df_juncao_voos, hide_index=True, use_container_width=True)

# Roteirizando Regiões

if roteirizar:

    nome_df_hotel = st.session_state.dict_regioes_hoteis[servico_roteiro][0]

    nome_html_ref = st.session_state.dict_regioes_hoteis[servico_roteiro][1]

    nome_aba_excel = st.session_state.dict_regioes_hoteis[servico_roteiro][2]

    nome_regiao = st.session_state.dict_regioes_hoteis[servico_roteiro][3]

    df_hoteis_ref = st.session_state[nome_df_hotel]

    sequencia_ritz = df_hoteis_ref.loc[df_hoteis_ref['Est Origem'] == 'RITZ SUITES', 'Sequência'].values[0]

    # Filtrando apenas data especificada, OUTs e Status do Serviço diferente de 'CANCELADO' e retirando os hoteis de piedade pra fazer o roteiro em separado

    df_router_filtrado = st.session_state.df_router[(st.session_state.df_router['Data Execucao']==data_roteiro) & 
                                                    (st.session_state.df_router['Tipo de Servico']=='OUT') &  
                                                    (st.session_state.df_router['Status do Servico']!='CANCELADO') & 
                                                    (st.session_state.df_router['Servico']==servico_roteiro)].reset_index(drop=True)
    
    # Categorizando serviços com 'EXCLUSIVO' na observação
    
    df_router_filtrado['Modo do Servico'] = df_router_filtrado.apply(
        lambda row: 'EXCLUSIVO' if verificar_exclusivo(row['Observacao']) else row['Modo do Servico'], axis=1)
    
    # Excluindo linhas onde exite 'CLD' na observação

    df_router_filtrado = df_router_filtrado[~df_router_filtrado['Observacao'].str.upper().str.contains('CLD', na=False)]
    
    # Verificando se todos os hoteis estão na lista da sequência
 
    itens_faltantes, lista_hoteis_df_router = gerar_itens_faltantes(df_router_filtrado, df_hoteis_ref)

    if len(itens_faltantes)==0:

        # Mensagens de andamento do script informando como foi a verificação dos hoteis cadastrados

        st.success('Todos os hoteis estão cadastrados na lista de sequência de hoteis')

        df_router_filtrado_2 = criar_df_servicos_2(df_router_filtrado, st.session_state.df_juncao_voos, df_hoteis_ref)

        roteiro = 0

        # Roteirizando Fretamentos

        df_fretamentos = df_router_filtrado_2[df_router_filtrado_2['Voo'].isin(voos_fret)].reset_index()

        df_escalas_in = st.session_state.vw_payment_guide[st.session_state.vw_payment_guide['Tipo de Servico']=='IN']\
            .reset_index(drop=True)

        df_fretamentos = pd.merge(df_fretamentos, df_escalas_in[['Reserva', 'Escala']], 
                                  on=['Reserva'], how='left')
        
        for index_2 in df_fretamentos['index'].tolist():

            df_router_filtrado_2 = df_router_filtrado_2.drop(index=index_2)
        
        df_fretamentos, roteiro = roteirizar_fretamentos(df_fretamentos, roteiro)

        # Criando dataframe que vai receber os hoteis que tem mais paxs que a capacidade máxima da frota

        lista_colunas = ['index']

        df_hoteis_pax_max = pd.DataFrame(columns=lista_colunas.extend(df_router_filtrado_2.columns.tolist()))

        # Roteirizando hoteis que podem receber ônibus com mais paxs que a capacidade máxima da frota

        df_router_filtrado_2, df_hoteis_pax_max, roteiro = \
            roteirizar_hoteis_mais_pax_max(df_router_filtrado_2, roteiro, df_hoteis_pax_max)

        df_juncoes_pax_max = pd.DataFrame()

        df_voos_pax_max = pd.DataFrame()

        df_router_filtrado_2['Horario Voo'] = pd.to_datetime(df_router_filtrado_2['Horario Voo'], format='%H:%M:%S').dt.time

        # Roteirizando com gerald os carros maiores especificados

        if robo_usado=='Gerald':

            df_router_filtrado_2, roteiro, df_juncoes_pax_max, df_voos_pax_max = \
                roteirizar_voo_juncao_mais_pax_max(df_router_filtrado_2, roteiro, max_hoteis, pax_max_gerald, 
                                                   df_hoteis_ref, intervalo_hoteis_bairros_iguais, intervalo_hoteis_bairros_diferentes, 
                                                   df_juncoes_pax_max, df_voos_pax_max) 

        # Gerando horários de apresentação

        df_router_filtrado_2, roteiro = gerar_horarios_apresentacao(df_router_filtrado_2, roteiro, max_hoteis)

    else:

        inserir_hoteis_faltantes(itens_faltantes, df_hoteis_ref, nome_aba_excel, nome_regiao)

        st.stop()

    # Gerando roteiros alternativos

    df_roteiros_alternativos = gerar_roteiros_alternativos(df_router_filtrado_2, max_hoteis)

    # Gerando roteiros alternativos 2

    max_hoteis_2 = 10

    intervalo_pu_hotel_2 = pd.Timedelta(hours=1)

    df_roteiros_alternativos_2 = gerar_roteiros_alternativos_2(df_router_filtrado_2, max_hoteis_2, intervalo_pu_hotel_2)

    # Identificando serviços das rotas primárias que vão precisar de apoios

    df_router_filtrado_2 = identificar_apoios_em_df(df_router_filtrado_2)

    # Gerando rotas de apoios de rotas primárias

    df_router_filtrado_2, df_roteiros_apoios = gerar_roteiros_apoio(df_router_filtrado_2)
    
    # Identificando serviços das rotas alternativas que vão precisar de apoios

    df_roteiros_alternativos = identificar_apoios_em_df(df_roteiros_alternativos)

    # Gerando rotas de apoios de rotas alternativas

    df_roteiros_alternativos, df_roteiros_apoios_alternativos = gerar_roteiros_apoio(df_roteiros_alternativos)

    if len(df_roteiros_alternativos_2)>0:

        # Identificando serviços das rotas alternativas 2 que vão precisar de apoios

        df_roteiros_alternativos_2 = identificar_apoios_em_df(df_roteiros_alternativos_2)

        # Gerando rotas de apoios de rotas alternativas 2

        df_roteiros_alternativos_2, df_roteiros_apoios_alternativos_2 = gerar_roteiros_apoio(df_roteiros_alternativos_2)

    # Plotando roteiros de cada carro

    st.divider()

    row_warning = st.columns(1)

    row3 = st.columns(3)

    coluna = 0

    st.session_state.nome_html = f"{str(data_roteiro.strftime('%d-%m-%Y'))} {nome_html_ref}.html"

    st.session_state.df_fretamentos = df_fretamentos

    st.session_state.df_hoteis_pax_max = df_hoteis_pax_max

    st.session_state.df_juncoes_pax_max = df_juncoes_pax_max

    st.session_state.df_voos_pax_max = df_voos_pax_max

    st.session_state.df_router_filtrado_2 = df_router_filtrado_2

    st.session_state.df_roteiros_alternativos = df_roteiros_alternativos

    st.session_state.df_roteiros_alternativos_2 = df_roteiros_alternativos_2

    st.session_state.df_roteiros_apoios = df_roteiros_apoios

    st.session_state.df_roteiros_apoios_alternativos = df_roteiros_apoios_alternativos

    st.session_state.df_roteiros_apoios_alternativos_2 = df_roteiros_apoios_alternativos_2

    verificar_rotas_alternativas_ou_plotar_roteiros(df_roteiros_alternativos, row_warning, row3, coluna, df_hoteis_pax_max, 
                                                    df_juncoes_pax_max, df_voos_pax_max, df_router_filtrado_2, df_roteiros_apoios, 
                                                    df_roteiros_apoios_alternativos, st.session_state.df_juncao_voos, 
                                                    st.session_state.nome_html)

# Gerar roteiros finais

if 'nome_html' in st.session_state and len(st.session_state.df_roteiros_alternativos)>0:

    st.divider()

    row_rotas_alternativas = st.columns(1)

    row3 = st.columns(3)

    coluna = 0

    lista_rotas_alternativas = st.session_state.df_roteiros_alternativos['Roteiro'].unique().tolist()

    lista_rotas_alternativas_2 = st.session_state.df_roteiros_alternativos_2['Roteiro'].unique().tolist()

    with row_rotas_alternativas[0]:

        rotas_alternativas = st.multiselect('Selecione as Rotas Alternativas que serão usadas', lista_rotas_alternativas)

        rotas_alternativas_2 = st.multiselect('Selecione as Rotas Alternativas 2 que serão usadas', lista_rotas_alternativas_2)
    
        gerar_roteiro_final = st.button('Gerar Roteiro Final')

    if not gerar_roteiro_final:
    
        coluna = plotar_roteiros_gerais_alternativos(st.session_state.df_router_filtrado_2, st.session_state.df_roteiros_apoios, 
                                                     st.session_state.df_roteiros_alternativos, 
                                                     st.session_state.df_roteiros_alternativos_2,
                                                     st.session_state.df_roteiros_apoios_alternativos, 
                                                     st.session_state.df_roteiros_apoios_alternativos_2, coluna, row3)
        
    else:

        if set(rotas_alternativas) & set(rotas_alternativas_2):

            st.error('Não pode selecionar a mesma rota na opção alternativa e opção alternativa 2.')

        else:

            if 'df_servico_voos_horarios' in st.session_state:
                
                st.session_state['df_servico_voos_horarios'] = pd.DataFrame(columns=['Servico', 'Voo', 'Horario Voo'])
        
            df_fretamentos = st.session_state.df_fretamentos

            df_hoteis_pax_max = st.session_state.df_hoteis_pax_max

            df_juncoes_pax_max = st.session_state.df_juncoes_pax_max

            df_voos_pax_max = st.session_state.df_voos_pax_max

            df_router_filtrado_2 = st.session_state.df_router_filtrado_2

            df_roteiros_apoios = st.session_state.df_roteiros_apoios

            df_roteiros_apoios_alternativos = st.session_state.df_roteiros_apoios_alternativos

            df_roteiros_apoios_alternativos_2 = st.session_state.df_roteiros_apoios_alternativos_2

            if len(rotas_alternativas)>0:

                df_roteiros_alternativos = st.session_state.df_roteiros_alternativos\
                    [st.session_state.df_roteiros_alternativos['Roteiro'].isin(rotas_alternativas)].reset_index(drop=True)
                
                df_router_filtrado_2 = df_router_filtrado_2[~df_router_filtrado_2['Roteiro'].isin(rotas_alternativas)]\
                    .reset_index(drop=True)
                
            else:

                df_roteiros_alternativos = pd.DataFrame(columns=st.session_state.df_roteiros_alternativos.columns.tolist())

            if len(rotas_alternativas_2)>0:

                df_roteiros_alternativos_2 = st.session_state.df_roteiros_alternativos_2\
                    [st.session_state.df_roteiros_alternativos_2['Roteiro'].isin(rotas_alternativas_2)].reset_index(drop=True)
                
                df_router_filtrado_2 = df_router_filtrado_2[~df_router_filtrado_2['Roteiro'].isin(rotas_alternativas_2)]\
                    .reset_index(drop=True)
                
                df_roteiros_alternativos = pd.concat([df_roteiros_alternativos, df_roteiros_alternativos_2], ignore_index=True)
                
            else:

                df_roteiros_alternativos_2 = pd.DataFrame(columns=st.session_state.df_roteiros_alternativos_2.columns.tolist())

            lista_dfs = [df_fretamentos, df_hoteis_pax_max, df_juncoes_pax_max, df_voos_pax_max, df_router_filtrado_2, 
                         df_roteiros_apoios, df_roteiros_alternativos]

            n_carros = 0

            for df in lista_dfs:
                
                if len(df)>0:

                    n_carros += len(df[['Roteiro', 'Carros']].drop_duplicates())

            with row_rotas_alternativas[0]:

                st.header(f'A roteirização usou um total de {n_carros} carros')

            if len(df_fretamentos)>0:

                coluna = plotar_roteiros_simples(df_fretamentos, row3, coluna)

            if len(df_hoteis_pax_max)>0:

                coluna = plotar_roteiros_simples(df_hoteis_pax_max, row3, coluna)

            if len(df_juncoes_pax_max)>0:

                coluna = plotar_roteiros_simples(df_juncoes_pax_max, row3, coluna)

            if len(df_voos_pax_max)>0:

                coluna = plotar_roteiros_simples(df_voos_pax_max, row3, coluna)

            coluna = plotar_roteiros_gerais_final(df_router_filtrado_2, df_roteiros_apoios, df_roteiros_alternativos, 
                                                  df_roteiros_apoios_alternativos, coluna)
            
            html = definir_html(st.session_state.df_juncao_voos)

            criar_output_html(st.session_state.nome_html, html)

            df_pdf = pd.concat([df_router_filtrado_2, df_fretamentos, df_hoteis_pax_max, df_juncoes_pax_max, df_voos_pax_max, 
                                df_roteiros_alternativos], ignore_index=True)
            
            for index in range(len(df_pdf)):

                tipo_de_servico_ref = df_pdf.at[index, 'Modo do Servico']

                juncao_ref_2 = df_pdf.at[index, 'Junção']

                if tipo_de_servico_ref == 'REGULAR' and not pd.isna(juncao_ref_2):

                    df_pdf.at[index, 'Horario Voo / Menor Horário'] = df_pdf.at[index, 'Menor Horário']

                elif (tipo_de_servico_ref == 'REGULAR' and pd.isna(juncao_ref_2)) or (tipo_de_servico_ref != 'REGULAR'):

                    df_pdf.at[index, 'Horario Voo / Menor Horário'] = df_pdf.at[index, 'Horario Voo']

            df_pdf = df_pdf.sort_values(by=['Horario Voo / Menor Horário', 'Junção']).reset_index(drop=True)

            inserir_roteiros_html(st.session_state.nome_html, df_pdf)

            with open(st.session_state.nome_html, "r", encoding="utf-8") as file:

                html_content = file.read()

            st.download_button(
                label="Baixar Arquivo HTML",
                data=html_content,
                file_name=st.session_state.nome_html,
                mime="text/html"
            )
